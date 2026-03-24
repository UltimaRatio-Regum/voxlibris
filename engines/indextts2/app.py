import os

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("HF_HUB_CACHE", "./checkpoints/hf_cache")

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
logger = logging.getLogger("indextts2-engine")

BEARER_TOKEN = os.environ.get("API_KEY", "")
SAMPLE_RATE = 22050
BIT_DEPTH = 16
CHANNELS = 1
MAX_SECONDS = 60
MAX_CHARS = 500

TOMEVOX_TO_INDEXTTS2_EMOTIONS = {
    "neutral": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.8],
    "happy": [0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
    "angry": [0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1],
    "sad": [0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.1],
    "fear": [0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.1],
    "disgust": [0.0, 0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.1],
    "melancholy": [0.0, 0.0, 0.2, 0.0, 0.0, 0.6, 0.0, 0.1],
    "surprise": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.7, 0.1],
    "calm": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.8],
    "excited": [0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.0],
    "anxious": [0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.2],
    "hopeful": [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3],
    "tender": [0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5],
    "proud": [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.2],
    "fearful": [0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.1],
    "confused": [0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.3, 0.3],
}

EMOTION_SPEED_MAP = {
    "neutral": 1.0,
    "happy": 1.02,
    "sad": 0.97,
    "angry": 1.04,
    "fear": 1.03,
    "fearful": 1.03,
    "surprise": 1.05,
    "disgust": 0.98,
    "excited": 1.03,
    "calm": 0.96,
    "confused": 0.98,
    "anxious": 1.02,
    "hopeful": 1.01,
    "melancholy": 0.96,
    "tender": 0.97,
    "proud": 1.01,
}

EMOTION_PITCH_MAP = {
    "neutral": 0.0,
    "happy": 0.5,
    "sad": -0.3,
    "angry": -0.2,
    "fear": 0.3,
    "fearful": 0.3,
    "surprise": 0.6,
    "disgust": -0.2,
    "excited": 0.7,
    "calm": -0.1,
    "confused": 0.2,
    "anxious": 0.3,
    "hopeful": 0.3,
    "melancholy": -0.4,
    "tender": -0.1,
    "proud": 0.2,
}

CANONICAL_EMOTIONS = [
    "neutral",
    "happy",
    "sad",
    "angry",
    "fear",
    "surprise",
    "disgust",
    "excited",
    "calm",
    "anxious",
    "hopeful",
    "melancholy",
    "tender",
    "proud",
    "fearful",
    "confused",
]

tts_model = None


def load_model():
    global tts_model
    from indextts.infer_v2 import IndexTTS2

    model_dir = os.environ.get("MODEL_DIR", "checkpoints")
    cfg_path = os.path.join(model_dir, "config.yaml")

    if not os.path.exists(cfg_path):
        logger.info(
            "Model not found locally, downloading IndexTeam/IndexTTS-2...")
        from huggingface_hub import snapshot_download
        snapshot_download("IndexTeam/IndexTTS-2", local_dir=model_dir)
        logger.info("Model download complete.")
    use_fp16 = os.environ.get("USE_FP16",
                              "true").lower() in ("true", "1", "yes")

    device = None
    if torch.cuda.is_available():
        device = "cuda:0"
    elif hasattr(torch, "mps") and torch.backends.mps.is_available():
        device = "mps"
        use_fp16 = False
    else:
        device = "cpu"
        use_fp16 = False

    logger.info(
        f"Loading IndexTTS2 model from {model_dir} on {device} (fp16={use_fp16})..."
    )
    tts_model = IndexTTS2(
        cfg_path=cfg_path,
        model_dir=model_dir,
        use_fp16=use_fp16,
        device=device,
    )
    logger.info("IndexTTS2 model loaded successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="IndexTTS2 Engine", lifespan=lifespan)


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


def blend_emotion_vectors(emotion_set: list[str],
                          intensity: int) -> list[float]:
    intensity_factor = intensity / 50.0

    if not emotion_set or emotion_set == ["neutral"]:
        base = TOMEVOX_TO_INDEXTTS2_EMOTIONS.get("neutral",
                                                   [0.0] * 7 + [0.8])
        return list(base)

    blended = [0.0] * 8
    count = 0
    for emo in emotion_set:
        emo_lower = emo.lower()
        vec = TOMEVOX_TO_INDEXTTS2_EMOTIONS.get(emo_lower)
        if vec:
            for i in range(8):
                blended[i] += vec[i]
            count += 1

    if count == 0:
        return list(TOMEVOX_TO_INDEXTTS2_EMOTIONS["neutral"])

    blended = [v / count for v in blended]

    for i in range(7):
        blended[i] = blended[i] * intensity_factor

    calm_remaining = max(0.0, 1.0 - sum(blended[:7]))
    blended[7] = min(blended[7], calm_remaining)

    return blended


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
        "engine_id": "indextts2",
        "engine_name": "IndexTTS2",
        "sample_rate": SAMPLE_RATE,
        "bit_depth": BIT_DEPTH,
        "channels": CHANNELS,
        "max_seconds_per_conversion": MAX_SECONDS,
        "supports_voice_cloning": True,
        "builtin_voices": [],
        "supported_emotions": CANONICAL_EMOTIONS,
        "extra_properties": {
            "model":
            "IndexTeam/IndexTTS-2",
            "max_characters":
            MAX_CHARS,
            "emotion_control":
            "8-dimensional emotion vectors via fine-tuned Qwen3",
            "features": [
                "zero-shot voice cloning",
                "emotion-speaker disentanglement",
                "duration control",
                "multilingual (Chinese, English)",
            ],
        }
    }


@app.post("/ConvertTextToSpeech")
async def convert_text_to_speech(request: Request):
    verify_auth(request)

    try:
        body = await request.json()
        req = ConvertRequest(**body)
    except Exception as e:
        return JSONResponse(status_code=400,
                            content={
                                "error": str(e),
                                "error_code": "INVALID_REQUEST"
                            })

    if not req.input_text.strip():
        return JSONResponse(status_code=400,
                            content={
                                "error": "Input text is empty",
                                "error_code": "INVALID_REQUEST"
                            })

    if not req.voice_to_clone_sample:
        return JSONResponse(
            status_code=400,
            content={
                "error": "IndexTTS2 requires a voice sample for cloning. "
                "Please provide a voice_to_clone_sample.",
                "error_code": "INVALID_REQUEST"
            })

    if req.random_seed is not None and req.random_seed > 0:
        torch.manual_seed(req.random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(req.random_seed)

    temp_files = []

    try:
        try:
            wav_bytes = base64.b64decode(req.voice_to_clone_sample,
                                         validate=True)
        except Exception:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid voice_to_clone_sample: not valid base64",
                    "error_code": "INVALID_REQUEST"
                })

        if len(wav_bytes) < 44:
            return JSONResponse(
                status_code=400,
                content={
                    "error":
                    "Invalid voice_to_clone_sample: file too small to be valid audio",
                    "error_code": "INVALID_REQUEST"
                })

        tmp_voice = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_voice.write(wav_bytes)
        tmp_voice.close()
        speaker_wav_path = tmp_voice.name
        temp_files.append(tmp_voice.name)

        tmp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_out.close()
        output_path = tmp_out.name
        temp_files.append(tmp_out.name)

        text = req.input_text.strip()
        if len(text) > MAX_CHARS:
            truncated = text[:MAX_CHARS]
            last_space = truncated.rfind(' ')
            if last_space > MAX_CHARS * 0.6:
                truncated = truncated[:last_space]
            text = truncated
            logger.warning(f"Text truncated to {len(text)} characters")

        if text and text[-1] not in '.!?;:。！？；：':
            text += '.'

        dominant_emotion = req.emotion_set[0].lower(
        ) if req.emotion_set else "neutral"
        emo_vector = blend_emotion_vectors(req.emotion_set, req.intensity)
        emo_vector = tts_model.normalize_emo_vec(emo_vector, apply_bias=True)

        emotion_speed = EMOTION_SPEED_MAP.get(dominant_emotion, 1.0)
        emotion_pitch = EMOTION_PITCH_MAP.get(dominant_emotion, 0.0)

        intensity_factor = req.intensity / 50.0
        emotion_speed = 1.0 + (emotion_speed - 1.0) * intensity_factor
        emotion_pitch = emotion_pitch * intensity_factor

        is_neutral = all(e.lower() in ("neutral", "calm")
                         for e in req.emotion_set)

        logger.info(f"Generating with IndexTTS2: emotions={req.emotion_set}, "
                    f"emo_vector={[f'{v:.2f}' for v in emo_vector]}, "
                    f"intensity={req.intensity}, text_len={len(text)}, "
                    f"is_neutral={is_neutral}")

        kwargs = {
            "spk_audio_prompt": speaker_wav_path,
            "text": text,
            "output_path": output_path,
            "verbose": False,
        }

        if not is_neutral:
            kwargs["emo_vector"] = emo_vector

        tts_model.infer(**kwargs)

        if not os.path.exists(output_path) or os.path.getsize(
                output_path) == 0:
            return JSONResponse(status_code=500,
                                content={
                                    "error": "IndexTTS2 produced no output",
                                    "error_code": "GENERATION_FAILED"
                                })

        import torchaudio
        wav_tensor, sr = torchaudio.load(output_path)
        audio_np = wav_tensor.squeeze().numpy().astype(np.float32)

        if sr != SAMPLE_RATE:
            import librosa
            audio_np = librosa.resample(audio_np,
                                        orig_sr=sr,
                                        target_sr=SAMPLE_RATE)

        peak = np.max(np.abs(audio_np))
        if peak > 0:
            audio_np = audio_np / peak

        speed_factor = emotion_speed
        if req.speed_adjust != 0.0:
            user_speed = 1.0 + (req.speed_adjust / 100.0)
            speed_factor = speed_factor * user_speed
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

        wav_bytes_out = numpy_to_wav_bytes(audio_np, SAMPLE_RATE)

        return Response(content=wav_bytes_out, media_type="audio/wav")

    except Exception as e:
        logger.exception("TTS generation failed")
        return JSONResponse(status_code=500,
                            content={
                                "error": "Audio generation failed",
                                "error_code": "GENERATION_FAILED",
                                "details": str(e)
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
    return HTMLResponse(content="""
    <html>
    <head><title>IndexTTS2 Engine</title></head>
    <body style="font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px;">
        <h1>IndexTTS2 Engine</h1>
        <p>TomeVox-compatible TTS engine powered by
           <a href="https://github.com/index-tts/index-tts">IndexTTS2</a>.</p>
        <h2>Endpoints</h2>
        <ul>
            <li><code>POST /GetEngineDetails</code> - Get engine capabilities</li>
            <li><code>POST /ConvertTextToSpeech</code> - Convert text to speech</li>
            <li><code>GET /health</code> - Health check</li>
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
