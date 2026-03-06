import os
import io
import base64
import tempfile
import logging
import wave
import numpy as np
import torch
import pyrubberband as pyrb
import soundfile as sf
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qwen3-tts-engine")

BEARER_TOKEN = os.environ.get("API_KEY", "")
MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
SAMPLE_RATE = 24000
BIT_DEPTH = 16
CHANNELS = 1
MAX_SECONDS = 30

BUILTIN_SPEAKERS = [
    {"id": "Vivian", "display_name": "Vivian", "extra_info": "Bright, slightly edgy young female voice (Chinese native)"},
    {"id": "Serena", "display_name": "Serena", "extra_info": "Warm, gentle young female voice (Chinese native)"},
    {"id": "Uncle_Fu", "display_name": "Uncle Fu", "extra_info": "Seasoned male voice with low, mellow timbre (Chinese native)"},
    {"id": "Dylan", "display_name": "Dylan", "extra_info": "Youthful male voice, clear and natural (Beijing dialect)"},
    {"id": "Eric", "display_name": "Eric", "extra_info": "Lively male voice with slightly husky brightness (Sichuan dialect)"},
    {"id": "Ryan", "display_name": "Ryan", "extra_info": "Dynamic male voice with strong rhythmic drive (English native)"},
    {"id": "Aiden", "display_name": "Aiden", "extra_info": "Sunny American male voice with clear midrange (English native)"},
    {"id": "Ono_Anna", "display_name": "Ono Anna", "extra_info": "Playful Japanese female voice, light and nimble (Japanese native)"},
    {"id": "Sohee", "display_name": "Sohee", "extra_info": "Warm Korean female voice with rich emotion (Korean native)"},
]

EMOTION_TO_INSTRUCT = {
    "neutral": "",
    "happy": "Speak with a happy, cheerful tone.",
    "sad": "Speak with a sad, melancholy tone.",
    "angry": "Speak with an angry, forceful tone.",
    "fear": "Speak with a fearful, trembling tone.",
    "surprise": "Speak with a surprised, astonished tone.",
    "excited": "Speak with an excited, energetic tone.",
    "calm": "Speak with a calm, soothing tone.",
    "disgust": "Speak with a disgusted tone.",
    "confused": "Speak with a confused, uncertain tone.",
    "anxious": "Speak with an anxious, worried tone.",
    "hopeful": "Speak with a hopeful, optimistic tone.",
    "melancholy": "Speak with a deeply melancholic tone.",
    "fearful": "Speak with a fearful, trembling tone.",
}

model = None
clone_model = None


def load_model():
    global model, clone_model
    from qwen_tts import Qwen3TTSModel

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    attn = "flash_attention_2" if torch.cuda.is_available() else "sdpa"

    logger.info(f"Loading Qwen3-TTS CustomVoice model on {device}...")
    model = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        device_map=device,
        dtype=dtype,
        attn_implementation=attn,
    )
    logger.info("Qwen3-TTS CustomVoice model loaded.")

    logger.info("Loading Qwen3-TTS Base model for voice cloning...")
    clone_model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        device_map=device,
        dtype=dtype,
        attn_implementation=attn,
    )
    logger.info("Qwen3-TTS Base model loaded.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="Qwen3 TTS Engine", lifespan=lifespan)


def verify_auth(request: Request):
    if not BEARER_TOKEN:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {BEARER_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def numpy_to_wav_bytes(audio_np: np.ndarray, sample_rate: int) -> bytes:
    audio_np = np.clip(audio_np, -1.0, 1.0)
    audio_int16 = (audio_np * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


class ConvertRequest(BaseModel):
    input_text: str
    builtin_voice_id: Optional[str] = None
    voice_to_clone_sample: Optional[str] = None
    random_seed: Optional[int] = None
    emotion_set: list[str] = Field(default_factory=lambda: ["neutral"])
    intensity: int = 50
    volume: int = 75
    speed_adjust: float = 0.0
    pitch_adjust: float = 0.0


@app.post("/GetEngineDetails")
async def get_engine_details(request: Request):
    verify_auth(request)

    return {
        "engine_id": "qwen3-tts",
        "engine_name": "Qwen3 TTS",
        "sample_rate": SAMPLE_RATE,
        "bit_depth": BIT_DEPTH,
        "channels": CHANNELS,
        "max_seconds_per_conversion": MAX_SECONDS,
        "supports_voice_cloning": True,
        "builtin_voices": BUILTIN_SPEAKERS,
        "supported_emotions": [
            "neutral", "happy", "sad", "angry", "fear",
            "surprise", "excited", "calm", "disgust",
            "confused", "anxious", "hopeful", "melancholy", "fearful"
        ],
        "extra_properties": {
            "model_custom_voice": MODEL_ID,
            "model_clone": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            "languages": [
                "English", "Chinese", "Japanese", "Korean"
            ],
            "features": [
                "instruct-based emotion control",
                "voice cloning with ref_audio + ref_text",
                "x_vector_only_mode for cloning without transcript"
            ]
        }
    }


@app.post("/ConvertTextToSpeech")
async def convert_text_to_speech(request: Request):
    verify_auth(request)

    try:
        body = await request.json()
        req = ConvertRequest(**body)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e), "error_code": "INVALID_REQUEST"}
        )

    if not req.input_text.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Input text is empty", "error_code": "INVALID_REQUEST"}
        )

    speaker_id = req.builtin_voice_id or "Ryan"
    known_ids = [v["id"] for v in BUILTIN_SPEAKERS]
    if speaker_id not in known_ids and not req.voice_to_clone_sample:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"Voice '{speaker_id}' not found",
                "error_code": "VOICE_NOT_FOUND",
                "details": f"Available voices: {', '.join(known_ids)}"
            }
        )

    if req.random_seed is not None:
        torch.manual_seed(req.random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(req.random_seed)

    temp_files = []

    try:
        instruct = ""
        if req.emotion_set:
            dominant = req.emotion_set[0]
            base_instruct = EMOTION_TO_INSTRUCT.get(dominant, "")
            if base_instruct:
                if req.intensity > 66:
                    instruct = base_instruct.replace("Speak with", "Speak with a very strong,")
                elif req.intensity < 33:
                    instruct = base_instruct.replace("Speak with", "Speak with a slightly")
                else:
                    instruct = base_instruct

        if req.voice_to_clone_sample:
            ref_audio_b64 = req.voice_to_clone_sample

            wavs, sr = clone_model.generate_voice_clone(
                text=req.input_text,
                language="Auto",
                ref_audio=ref_audio_b64,
                ref_text="",
                x_vector_only_mode=True,
            )
        else:
            generate_kwargs = {
                "text": req.input_text,
                "language": "Auto",
                "speaker": speaker_id,
            }
            if instruct:
                generate_kwargs["instruct"] = instruct

            wavs, sr = model.generate_custom_voice(**generate_kwargs)

        audio_np = np.array(wavs[0], dtype=np.float32)

        max_val = np.max(np.abs(audio_np))
        if max_val > 0:
            audio_np = audio_np / max_val

        speed = 1.0 + (req.speed_adjust / 100.0)
        speed = max(0.5, min(2.0, speed))
        if speed != 1.0:
            audio_np = pyrb.time_stretch(audio_np, sr, speed)

        if req.pitch_adjust != 0.0:
            semitones = req.pitch_adjust * 0.24
            audio_np = pyrb.pitch_shift(audio_np, sr, semitones)

        vol_factor = req.volume / 75.0
        audio_np = audio_np * vol_factor

        output_sr = sr if sr else SAMPLE_RATE
        wav_bytes = numpy_to_wav_bytes(audio_np, output_sr)

        return Response(content=wav_bytes, media_type="audio/wav")

    except Exception as e:
        logger.exception("TTS generation failed")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Audio generation failed",
                "error_code": "GENERATION_FAILED",
                "details": str(e)
            }
        )
    finally:
        for f in temp_files:
            try:
                os.unlink(f)
            except OSError:
                pass


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(content=html_path.read_text())


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "custom_voice_model_loaded": model is not None,
        "clone_model_loaded": clone_model is not None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
