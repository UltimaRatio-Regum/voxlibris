import os
os.environ.setdefault("OMP_NUM_THREADS", "4")

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
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("styletts2-engine")

BEARER_TOKEN = os.environ.get("API_KEY", "")
SAMPLE_RATE = 24000
BIT_DEPTH = 16
CHANNELS = 1
MAX_SECONDS = 60

EMOTION_PRESETS = {
    "neutral": {"alpha": 0.3, "beta": 0.7, "embedding_scale": 1, "diffusion_steps": 5},
    "happy": {"alpha": 0.1, "beta": 0.9, "embedding_scale": 2, "diffusion_steps": 10},
    "sad": {"alpha": 0.1, "beta": 0.9, "embedding_scale": 2, "diffusion_steps": 10},
    "angry": {"alpha": 0.1, "beta": 0.9, "embedding_scale": 2, "diffusion_steps": 10},
    "fear": {"alpha": 0.1, "beta": 0.9, "embedding_scale": 2, "diffusion_steps": 10},
    "excited": {"alpha": 0.05, "beta": 0.95, "embedding_scale": 2.5, "diffusion_steps": 10},
    "calm": {"alpha": 0.5, "beta": 0.5, "embedding_scale": 1, "diffusion_steps": 5},
    "surprise": {"alpha": 0.1, "beta": 0.9, "embedding_scale": 2, "diffusion_steps": 10},
    "surprised": {"alpha": 0.1, "beta": 0.9, "embedding_scale": 2, "diffusion_steps": 10},
    "whisper": {"alpha": 0.5, "beta": 0.3, "embedding_scale": 0.5, "diffusion_steps": 10},
}

tts_engine = None


def ensure_nltk_data():
    import nltk
    for pkg in ['punkt', 'punkt_tab', 'averaged_perceptron_tagger_eng']:
        try:
            nltk.data.find(f'tokenizers/{pkg}' if 'punkt' in pkg else f'taggers/{pkg}')
        except LookupError:
            nltk.download(pkg)


def load_model():
    global tts_engine
    ensure_nltk_data()

    _original_load = torch.load
    def _patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _original_load(*args, **kwargs)
    torch.load = _patched_load

    from styletts2 import tts as styletts2_tts

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading StyleTTS2 model on {device}...")

    tts_engine = styletts2_tts.StyleTTS2()
    logger.info("StyleTTS2 model loaded successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="StyleTTS2 TTS Engine", lifespan=lifespan)


def verify_auth(request: Request):
    if not BEARER_TOKEN:
        return None
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {BEARER_TOKEN}":
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "error_code": "UNAUTHORIZED"}
        )
    return None


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
    auth_err = verify_auth(request)
    if auth_err:
        return auth_err

    return {
        "engine_id": "styletts2",
        "engine_name": "StyleTTS2",
        "sample_rate": SAMPLE_RATE,
        "bit_depth": BIT_DEPTH,
        "channels": CHANNELS,
        "max_seconds_per_conversion": MAX_SECONDS,
        "supports_voice_cloning": True,
        "builtin_voices": [],
        "supported_emotions": ["neutral", "happy", "sad", "angry", "fear", "excited", "calm", "surprise", "whisper"],
        "extra_properties": {
            "architecture": "Style diffusion + adversarial training with large SLMs",
            "model": "LibriTTS multi-speaker",
            "parameters": {
                "alpha": "Timbre control (0=reference voice, 1=text-predicted style)",
                "beta": "Prosody control (0=reference voice, 1=text-predicted style)",
                "embedding_scale": "Expressiveness (higher=more emotional)",
                "diffusion_steps": "Style diversity (more steps=more varied)",
            }
        }
    }


@app.post("/ConvertTextToSpeech")
async def convert_text_to_speech(request: Request):
    auth_err = verify_auth(request)
    if auth_err:
        return auth_err

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

    if req.random_seed is not None:
        torch.manual_seed(req.random_seed)
        np.random.seed(req.random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(req.random_seed)

    temp_files = []

    try:
        emotion = "neutral"
        if req.emotion_set and req.emotion_set[0] in EMOTION_PRESETS:
            emotion = req.emotion_set[0]

        preset = EMOTION_PRESETS[emotion].copy()

        if req.intensity != 50:
            scale_factor = req.intensity / 50.0
            preset["embedding_scale"] = preset["embedding_scale"] * scale_factor
            preset["embedding_scale"] = max(0.1, min(5.0, preset["embedding_scale"]))

        ref_wav_path = None
        if req.voice_to_clone_sample:
            try:
                wav_bytes = base64.b64decode(req.voice_to_clone_sample)
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Invalid base64 in voice_to_clone_sample", "error_code": "INVALID_REQUEST"}
                )

            if len(wav_bytes) < 100:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Voice clone sample is too small", "error_code": "INVALID_REQUEST"}
                )

            tmp_ref = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_ref.write(wav_bytes)
            tmp_ref.close()
            temp_files.append(tmp_ref.name)

            try:
                sf.read(tmp_ref.name)
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Voice clone sample is not valid audio", "error_code": "INVALID_REQUEST"}
                )

            ref_wav_path = tmp_ref.name

        text = req.input_text.strip()
        is_long = len(text) > 200 or text.count('.') > 2

        if is_long:
            wav = tts_engine.long_inference(
                text,
                target_voice_path=ref_wav_path,
                output_sample_rate=SAMPLE_RATE,
                alpha=preset["alpha"],
                beta=preset["beta"],
                t=0.7,
                diffusion_steps=preset["diffusion_steps"],
                embedding_scale=preset["embedding_scale"],
            )
        else:
            wav = tts_engine.inference(
                text,
                target_voice_path=ref_wav_path,
                output_sample_rate=SAMPLE_RATE,
                alpha=preset["alpha"],
                beta=preset["beta"],
                diffusion_steps=preset["diffusion_steps"],
                embedding_scale=preset["embedding_scale"],
            )

        audio_np = np.array(wav, dtype=np.float32)

        max_val = np.max(np.abs(audio_np))
        if max_val > 0:
            audio_np = audio_np / max_val

        if req.speed_adjust != 0.0:
            speed_factor = 1.0 + (req.speed_adjust / 100.0)
            speed_factor = max(0.5, min(2.0, speed_factor))
            audio_np = pyrb.time_stretch(audio_np, SAMPLE_RATE, speed_factor)

        if req.pitch_adjust != 0.0:
            semitones = req.pitch_adjust * 0.24
            audio_np = pyrb.pitch_shift(audio_np, SAMPLE_RATE, semitones)

        vol_factor = req.volume / 75.0
        audio_np = audio_np * vol_factor

        wav_bytes = numpy_to_wav_bytes(audio_np, SAMPLE_RATE)

        return Response(content=wav_bytes, media_type="audio/wav")

    except Exception as e:
        logger.exception("TTS generation failed")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Audio generation failed",
                "error_code": "GENERATION_FAILED",
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
        "model_loaded": tts_engine is not None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
