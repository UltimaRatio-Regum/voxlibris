import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "4")

# glmtts_inference.py lives in the same directory as this file (the cloned
# GLM-TTS repo root).  Adding it to sys.path lets us import it directly.
GLMTTS_DIR = os.path.dirname(os.path.abspath(__file__))
if GLMTTS_DIR not in sys.path:
    sys.path.insert(0, GLMTTS_DIR)

import io
import base64
import tempfile
import logging
import wave
import numpy as np
import torch
import pyrubberband as pyrb
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("glm-tts-engine")

BEARER_TOKEN = os.environ.get("API_KEY", "")
SAMPLE_RATE = 24000
BIT_DEPTH = 16
CHANNELS = 1
MAX_SECONDS = 30
MAX_CHARS = 500

# ---------------------------------------------------------------------------
# Emotion → prosody tables
# GLM-TTS does not expose internal emotion parameters; we emulate emotions
# through post-processing speed and pitch shifts (same strategy as XTTSv2).
# ---------------------------------------------------------------------------

EMOTION_SPEED_MAP = {
    "neutral":   1.00,
    "happy":     1.04,
    "sad":       0.93,
    "angry":     1.06,
    "fear":      1.05,
    "fearful":   1.05,
    "surprise":  1.07,
    "disgust":   0.97,
    "excited":   1.06,
    "calm":      0.94,
    "confused":  0.97,
    "anxious":   1.04,
    "hopeful":   1.02,
    "melancholy":0.92,
}

EMOTION_PITCH_MAP = {
    "neutral":    0.0,
    "happy":      0.6,
    "sad":       -0.4,
    "angry":     -0.3,
    "fear":       0.4,
    "fearful":    0.4,
    "surprise":   0.7,
    "disgust":   -0.3,
    "excited":    0.8,
    "calm":      -0.2,
    "confused":   0.2,
    "anxious":    0.4,
    "hopeful":    0.4,
    "melancholy": -0.5,
}

CANONICAL_EMOTIONS = [
    "neutral", "happy", "sad", "angry", "fear", "surprise",
    "disgust", "excited", "calm", "confused", "anxious",
    "hopeful", "melancholy", "fearful",
]

# ---------------------------------------------------------------------------
# Global model state
# ---------------------------------------------------------------------------

_frontend = None
_text_frontend = None
_llm = None
_flow = None
_device = "cuda" if torch.cuda.is_available() else "cpu"


def _download_model_if_needed():
    """Download GLM-TTS checkpoint from HuggingFace if not already present."""
    ckpt_dir = os.path.join(GLMTTS_DIR, "ckpt")
    llm_dir = os.path.join(ckpt_dir, "llm")
    if os.path.isdir(llm_dir) and os.listdir(llm_dir):
        logger.info("GLM-TTS checkpoint already present, skipping download.")
        return
    logger.info("Downloading GLM-TTS checkpoint from HuggingFace Hub…")
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id="zai-org/GLM-TTS", local_dir=ckpt_dir)
    logger.info("Download complete.")


def load_model():
    global _frontend, _text_frontend, _llm, _flow

    # Ensure checkpoint is available before importing glmtts_inference,
    # which resolves paths relative to the current working directory.
    _download_model_if_needed()

    # Change working directory so that glmtts_inference's hardcoded "ckpt/"
    # paths resolve correctly.
    os.chdir(GLMTTS_DIR)

    from glmtts_inference import load_models  # noqa: PLC0415
a
    logger.info(f"Loading GLM-TTS model on {_device}…")
    _frontend, _text_frontend, _, _llm, _flow = load_models(
        use_phoneme=False, sample_rate=SAMPLE_RATE
    )
    logger.info("GLM-TTS model loaded successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="GLM-TTS Engine", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class ConvertRequest(BaseModel):
    input_text: str
    builtin_voice_id: Optional[str] = None
    voice_to_clone_sample: Optional[str] = None
    random_seed: Optional[int] = None
    emotion_set: list[str] = Field(default_factory=lambda: ["neutral"])
    intensity: int = Field(default=50, ge=1, le=100)
    volume: int = Field(default=75, ge=1, le=100)
    speed_adjust: float = Field(default=0.0, ge=-5.0, le=5.0)
    pitch_adjust: float = Field(default=0.0, ge=-5.0, le=5.0)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/GetEngineDetails")
async def get_engine_details(request: Request):
    verify_auth(request)
    return {
        "engine_id": "glm-tts",
        "engine_name": "GLM-TTS",
        "sample_rate": SAMPLE_RATE,
        "bit_depth": BIT_DEPTH,
        "channels": CHANNELS,
        "max_seconds_per_conversion": MAX_SECONDS,
        "supports_voice_cloning": True,
        "builtin_voices": [],
        "supported_emotions": CANONICAL_EMOTIONS,
        "extra_properties": {
            "model": "zai-org/GLM-TTS",
            "max_characters": MAX_CHARS,
            "languages": ["zh", "en", "zh-en"],
        },
    }


@app.post("/ConvertTextToSpeech")
async def convert_text_to_speech(request: Request):
    verify_auth(request)

    try:
        body = await request.json()
        req = ConvertRequest(**body)
    except Exception as e:
        return JSONResponse(status_code=400, content={
            "error": str(e), "error_code": "INVALID_REQUEST"
        })

    if not req.input_text.strip():
        return JSONResponse(status_code=400, content={
            "error": "Input text is empty", "error_code": "INVALID_REQUEST"
        })

    if not req.voice_to_clone_sample:
        return JSONResponse(status_code=400, content={
            "error": (
                "GLM-TTS requires a reference voice sample for zero-shot cloning. "
                "Please provide voice_to_clone_sample."
            ),
            "error_code": "CLONING_NOT_SUPPORTED",
        })

    temp_files = []
    try:
        # Decode reference audio
        try:
            wav_bytes = base64.b64decode(req.voice_to_clone_sample, validate=True)
        except Exception:
            return JSONResponse(status_code=400, content={
                "error": "Invalid voice_to_clone_sample: not valid base64",
                "error_code": "INVALID_REQUEST",
            })

        if len(wav_bytes) < 44:
            return JSONResponse(status_code=400, content={
                "error": "Invalid voice_to_clone_sample: file too small to be valid audio",
                "error_code": "INVALID_REQUEST",
            })

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(wav_bytes)
        tmp.close()
        ref_path = tmp.name
        temp_files.append(ref_path)

        text = req.input_text.strip()
        if len(text) > MAX_CHARS:
            truncated = text[:MAX_CHARS]
            last_space = truncated.rfind(" ")
            if last_space > MAX_CHARS * 0.6:
                truncated = truncated[:last_space]
            text = truncated
            logger.warning(f"Text truncated to {len(text)} characters")

        if text and text[-1] not in ".!?;:":
            text += "."

        # Resolve dominant emotion and compute prosody scalars
        dominant = (req.emotion_set[0].lower() if req.emotion_set else "neutral")
        intensity_factor = req.intensity / 50.0  # 1.0 at default intensity 50

        base_speed = EMOTION_SPEED_MAP.get(dominant, 1.0)
        base_pitch = EMOTION_PITCH_MAP.get(dominant, 0.0)

        emotion_speed = 1.0 + (base_speed - 1.0) * intensity_factor
        emotion_pitch = base_pitch * intensity_factor

        seed = req.random_seed if req.random_seed is not None else 0
        if seed:
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed(seed)

        logger.info(
            f"Generating GLM-TTS: emotion={dominant} intensity={req.intensity} "
            f"emotion_speed={emotion_speed:.3f} emotion_pitch={emotion_pitch:.2f} "
            f"text_len={len(text)}"
        )

        # ------------------------------------------------------------------ #
        # Feature extraction from reference audio                             #
        # ------------------------------------------------------------------ #
        from glmtts_inference import generate_long  # noqa: PLC0415

        norm_prompt = _text_frontend.text_normalize("") + " "
        norm_input = _text_frontend.text_normalize(text)

        prompt_text_token = _frontend._extract_text_token(norm_prompt)
        prompt_speech_token = _frontend._extract_speech_token([ref_path])

        try:
            speech_feat = _frontend._extract_speech_feat(
                ref_path, sample_rate=SAMPLE_RATE
            )
        except TypeError:
            # Older build of the repo may not accept sample_rate kwarg
            speech_feat = _frontend._extract_speech_feat(ref_path)

        embedding = _frontend._extract_spk_embedding(ref_path)

        cache_speech_token_list = [prompt_speech_token.squeeze().tolist()]
        flow_prompt_token = torch.tensor(
            cache_speech_token_list, dtype=torch.int32
        ).to(_device)

        cache = {
            "cache_text": [norm_prompt],
            "cache_text_token": [prompt_text_token],
            "cache_speech_token": cache_speech_token_list,
            "use_cache": True,
        }

        # ------------------------------------------------------------------ #
        # Inference                                                            #
        # ------------------------------------------------------------------ #
        tts_speech, _, _, _ = generate_long(
            frontend=_frontend,
            text_frontend=_text_frontend,
            llm=_llm,
            flow=_flow,
            text_info=["", norm_input],
            cache=cache,
            embedding=embedding,
            flow_prompt_token=flow_prompt_token,
            speech_feat=speech_feat,
            sample_method="ras",
            seed=seed,
            device=_device,
            use_phoneme=False,
        )

        audio_np = tts_speech.squeeze().cpu().numpy().astype(np.float32)

        # ------------------------------------------------------------------ #
        # Post-processing: prosody + volume                                   #
        # ------------------------------------------------------------------ #
        speed_factor = emotion_speed
        if req.speed_adjust != 0.0:
            speed_factor *= 1.0 + (req.speed_adjust / 100.0)
        speed_factor = max(0.5, min(2.0, speed_factor))
        if abs(speed_factor - 1.0) > 0.01:
            audio_np = pyrb.time_stretch(audio_np, SAMPLE_RATE, speed_factor)

        total_pitch = emotion_pitch
        if req.pitch_adjust != 0.0:
            total_pitch += req.pitch_adjust * 0.24
        if abs(total_pitch) > 0.01:
            audio_np = pyrb.pitch_shift(audio_np, SAMPLE_RATE, total_pitch)

        vol_factor = req.volume / 75.0
        audio_np = audio_np * vol_factor

        wav_out = numpy_to_wav_bytes(audio_np, SAMPLE_RATE)
        return Response(content=wav_out, media_type="audio/wav")

    except Exception as e:
        logger.exception("TTS generation failed")
        return JSONResponse(status_code=500, content={
            "error": "Audio generation failed",
            "error_code": "GENERATION_FAILED",
            "details": str(e),
        })
    finally:
        for f in temp_files:
            try:
                os.unlink(f)
            except OSError:
                pass


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse(content="<h1>GLM-TTS Engine</h1>")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": _llm is not None,
        "device": _device,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
