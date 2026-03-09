"""
Remote TTS Engine Client

Calls external TTS engines via the VoxLibris TTS API Contract.
Handles GetEngineDetails and ConvertTextToSpeech endpoints.
"""

import base64
import logging
import httpx
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TIMEOUT_DETAILS = 15.0
TIMEOUT_TTS = 120.0


@dataclass
class BuiltinVoice:
    id: str
    display_name: str
    extra_info: Optional[str] = None
    voice_sample_url: Optional[str] = None


@dataclass
class EngineDetails:
    engine_id: str
    engine_name: str
    sample_rate: int
    bit_depth: int
    channels: int
    max_seconds_per_conversion: int
    supports_voice_cloning: bool
    builtin_voices: List[BuiltinVoice] = field(default_factory=list)
    supported_emotions: List[str] = field(default_factory=list)
    extra_properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSRequest:
    input_text: str
    builtin_voice_id: Optional[str] = None
    voice_to_clone_sample: Optional[bytes] = None
    random_seed: Optional[int] = None
    emotion_set: List[str] = field(default_factory=lambda: ["neutral"])
    intensity: int = 50
    volume: int = 75
    speed_adjust: float = 0.0
    pitch_adjust: float = 0.0


def normalize_hf_spaces_url(url: str) -> str:
    import re
    url = url.rstrip("/")
    m = re.match(r"https?://huggingface\.co/spaces/([^/]+)/([^/]+)(?:/.*)?$", url)
    if m:
        owner = m.group(1)
        space = m.group(2)
        return f"https://{owner}-{space}.hf.space"
    return url


class RemoteTTSClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None):
        self.base_url = normalize_hf_spaces_url(base_url.rstrip("/"))
        self.api_key = api_key

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def get_engine_details(self) -> EngineDetails:
        async with httpx.AsyncClient(timeout=TIMEOUT_DETAILS) as client:
            resp = await client.post(
                f"{self.base_url}/GetEngineDetails",
                json={},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        voices = []
        for v in data.get("builtin_voices", []):
            voices.append(BuiltinVoice(
                id=v["id"],
                display_name=v["display_name"],
                extra_info=v.get("extra_info"),
                voice_sample_url=v.get("voice_sample_url"),
            ))

        return EngineDetails(
            engine_id=data["engine_id"],
            engine_name=data["engine_name"],
            sample_rate=data["sample_rate"],
            bit_depth=data["bit_depth"],
            channels=data["channels"],
            max_seconds_per_conversion=data["max_seconds_per_conversion"],
            supports_voice_cloning=data["supports_voice_cloning"],
            builtin_voices=voices,
            supported_emotions=data.get("supported_emotions", []),
            extra_properties=data.get("extra_properties", {}),
        )

    async def convert_text_to_speech(self, request: TTSRequest) -> bytes:
        payload: Dict[str, Any] = {
            "input_text": request.input_text,
            "builtin_voice_id": request.builtin_voice_id,
            "voice_to_clone_sample": None,
            "random_seed": request.random_seed,
            "emotion_set": request.emotion_set,
            "intensity": request.intensity,
            "volume": request.volume,
            "speed_adjust": request.speed_adjust,
            "pitch_adjust": request.pitch_adjust,
        }

        if request.voice_to_clone_sample:
            payload["voice_to_clone_sample"] = base64.b64encode(
                request.voice_to_clone_sample
            ).decode("ascii")

        async with httpx.AsyncClient(timeout=TIMEOUT_TTS) as client:
            resp = await client.post(
                f"{self.base_url}/ConvertTextToSpeech",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "audio" in content_type or "octet-stream" in content_type:
            return resp.content

        error_data = resp.json() if "json" in content_type else {}
        raise RuntimeError(
            f"TTS engine returned unexpected content-type: {content_type}. "
            f"Error: {error_data.get('error', 'unknown')}"
        )
