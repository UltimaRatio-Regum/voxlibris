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
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatterbox-engine")

BEARER_TOKEN = os.environ.get("API_KEY", "")
SAMPLE_RATE = 24000
BIT_DEPTH = 16
CHANNELS = 1
MAX_SECONDS = 30
MAX_CHARS = 300

EMOTION_EXAGGERATION_MAP = {
    "neutral": 0.5,
    "happy": 0.7,
    "sad": 0.6,
    "angry": 0.85,
    "fear": 0.75,
    "fearful": 0.75,
    "surprise": 0.8,
    "disgust": 0.7,
    "excited": 0.9,
    "calm": 0.4,
    "confused": 0.5,
    "anxious": 0.75,
    "hopeful": 0.6,
    "melancholy": 0.55,
}

EMOTION_CFG_MAP = {
    "neutral": 0.5,
    "happy": 0.3,
    "sad": 0.6,
    "angry": 0.3,
    "fear": 0.4,
    "fearful": 0.4,
    "surprise": 0.3,
    "disgust": 0.5,
    "excited": 0.2,
    "calm": 0.7,
    "confused": 0.5,
    "anxious": 0.4,
    "hopeful": 0.4,
    "melancholy": 0.6,
}

CANONICAL_EMOTIONS = [
    "neutral", "happy", "sad", "angry", "fear",
    "surprise", "disgust", "excited", "calm", "confused",
    "anxious", "hopeful", "melancholy", "fearful",
]

tts_model = None


def load_model():
    global tts_model
    from chatterbox.tts import ChatterboxTTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading Chatterbox TTS model on {device}...")
    tts_model = ChatterboxTTS.from_pretrained(device=device)
    logger.info("Chatterbox TTS model loaded successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="Chatterbox TTS Engine", lifespan=lifespan)


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
    intensity: int = Field(default=50, ge=1, le=100)
    volume: int = Field(default=75, ge=1, le=100)
    speed_adjust: float = Field(default=0.0, ge=-5.0, le=5.0)
    pitch_adjust: float = Field(default=0.0, ge=-5.0, le=5.0)


@app.post("/GetEngineDetails")
async def get_engine_details(request: Request):
    verify_auth(request)

    return {
        "engine_id": "chatterbox",
        "engine_name": "Chatterbox TTS",
        "sample_rate": SAMPLE_RATE,
        "bit_depth": BIT_DEPTH,
        "channels": CHANNELS,
        "max_seconds_per_conversion": MAX_SECONDS,
        "supports_voice_cloning": True,
        "builtin_voices": [],
        "supported_emotions": CANONICAL_EMOTIONS,
        "extra_properties": {
            "model": "ResembleAI/chatterbox",
            "max_characters": MAX_CHARS,
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

    if not req.voice_to_clone_sample:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Chatterbox requires a voice sample for cloning. "
                         "Please provide a voice_to_clone_sample.",
                "error_code": "CLONING_NOT_SUPPORTED"
            }
        )

    if req.random_seed is not None and req.random_seed > 0:
        torch.manual_seed(req.random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(req.random_seed)

    temp_files = []

    try:
        try:
            wav_bytes = base64.b64decode(req.voice_to_clone_sample, validate=True)
        except Exception:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid voice_to_clone_sample: not valid base64",
                    "error_code": "INVALID_REQUEST"
                }
            )

        if len(wav_bytes) < 44:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid voice_to_clone_sample: file too small to be valid audio",
                    "error_code": "INVALID_REQUEST"
                }
            )

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(wav_bytes)
        tmp.close()
        speaker_wav_path = tmp.name
        temp_files.append(tmp.name)

        text = req.input_text
        if len(text) > MAX_CHARS:
            truncated = text[:MAX_CHARS]
            last_space = truncated.rfind(' ')
            if last_space > MAX_CHARS * 0.6:
                truncated = truncated[:last_space]
            text = truncated
            logger.warning(f"Text truncated to {len(text)} characters")

        dominant_emotion = req.emotion_set[0].lower() if req.emotion_set else "neutral"
        base_exaggeration = EMOTION_EXAGGERATION_MAP.get(dominant_emotion, 0.5)
        intensity_factor = req.intensity / 50.0
        exaggeration = min(1.0, max(0.0, base_exaggeration * intensity_factor))

        cfg_weight = EMOTION_CFG_MAP.get(dominant_emotion, 0.5)

        temperature = 0.8

        logger.info(
            f"Generating with Chatterbox: emotion={dominant_emotion}, "
            f"exaggeration={exaggeration:.2f}, cfg={cfg_weight:.2f}, "
            f"text_len={len(text)}"
        )

        wav = tts_model.generate(
            text,
            audio_prompt_path=speaker_wav_path,
            exaggeration=exaggeration,
            temperature=temperature,
            cfg_weight=cfg_weight,
        )

        audio_np = wav.squeeze().cpu().numpy().astype(np.float32)

        if req.speed_adjust != 0.0:
            speed_factor = 1.0 + (req.speed_adjust / 100.0)
            speed_factor = max(0.5, min(2.0, speed_factor))
            if abs(speed_factor - 1.0) > 0.01:
                audio_np = pyrb.time_stretch(audio_np, SAMPLE_RATE, speed_factor)

        if req.pitch_adjust != 0.0:
            semitones = req.pitch_adjust * 0.24
            audio_np = pyrb.pitch_shift(audio_np, SAMPLE_RATE, semitones)

        vol_factor = req.volume / 75.0
        audio_np = audio_np * vol_factor

        wav_bytes_out = numpy_to_wav_bytes(audio_np, SAMPLE_RATE)

        return Response(content=wav_bytes_out, media_type="audio/wav")

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
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse(content="""
    <html>
    <head><title>Chatterbox TTS Engine</title></head>
    <body style="font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px;">
        <h1>Chatterbox TTS Engine</h1>
        <p>VoxLibris-compatible TTS engine powered by <a href="https://github.com/resemble-ai/chatterbox">Chatterbox TTS</a>.</p>
        <h2>Endpoints</h2>
        <ul>
            <li><code>POST /GetEngineDetails</code> - Get engine capabilities</li>
            <li><code>POST /ConvertTextToSpeech</code> - Convert text to speech</li>
            <li><code>GET /health</code> - Health check</li>
        </ul>
        <h2>Features</h2>
        <ul>
            <li>Voice cloning from reference audio</li>
            <li>Emotion-driven expressiveness via exaggeration control</li>
            <li>Speed and pitch adjustment via pyrubberband</li>
        </ul>
    </body>
    </html>
    """)


@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": tts_model is not None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
