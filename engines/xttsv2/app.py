import os
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
logger = logging.getLogger("xttsv2-engine")

BEARER_TOKEN = os.environ.get("API_KEY", "")
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
SAMPLE_RATE = 24000
BIT_DEPTH = 16
CHANNELS = 1
MAX_SECONDS = 30

tts_model = None


def load_model():
    global tts_model
    from TTS.api import TTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Loading XTTSv2 model on {device}...")
    tts_model = TTS(model_name=MODEL_NAME, progress_bar=True).to(device)
    logger.info("XTTSv2 model loaded successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="XTTSv2 TTS Engine", lifespan=lifespan)


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
        "engine_id": "xttsv2",
        "engine_name": "Coqui XTTSv2",
        "sample_rate": SAMPLE_RATE,
        "bit_depth": BIT_DEPTH,
        "channels": CHANNELS,
        "max_seconds_per_conversion": MAX_SECONDS,
        "supports_voice_cloning": True,
        "builtin_voices": [],
        "supported_emotions": [
            "neutral", "happy", "sad", "angry", "fear",
            "surprise", "excited", "calm"
        ],
        "extra_properties": {
            "model": MODEL_NAME,
            "languages": [
                "en", "es", "fr", "de", "it", "pt", "pl", "tr",
                "ru", "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko"
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

    if req.random_seed is not None:
        torch.manual_seed(req.random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(req.random_seed)

    speaker_wav_path = None
    temp_files = []

    try:
        if req.voice_to_clone_sample:
            wav_bytes = base64.b64decode(req.voice_to_clone_sample)
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(wav_bytes)
            tmp.close()
            speaker_wav_path = tmp.name
            temp_files.append(tmp.name)

        speed = 1.0 + (req.speed_adjust / 100.0)
        speed = max(0.5, min(2.0, speed))

        emotion_prompt = ""
        if req.emotion_set and req.emotion_set[0] != "neutral":
            dominant = req.emotion_set[0]
            intensity_word = "slightly" if req.intensity < 33 else ("very" if req.intensity > 66 else "")
            emotion_prompt = f"[{intensity_word} {dominant}] " if intensity_word else f"[{dominant}] "

        synth_text = emotion_prompt + req.input_text

        language = "en"

        if speaker_wav_path:
            audio = tts_model.tts(
                text=synth_text,
                speaker_wav=speaker_wav_path,
                language=language,
                speed=speed,
            )
        else:
            audio = tts_model.tts(
                text=synth_text,
                language=language,
                speed=speed,
            )

        audio_np = np.array(audio, dtype=np.float32)

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
    return {"status": "ok", "model_loaded": tts_model is not None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
