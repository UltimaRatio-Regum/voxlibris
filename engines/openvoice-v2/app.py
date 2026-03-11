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
logger = logging.getLogger("openvoice-v2-engine")

BEARER_TOKEN = os.environ.get("API_KEY", "")
SAMPLE_RATE = 44100
BIT_DEPTH = 16
CHANNELS = 1
MAX_SECONDS = 30

CANONICAL_EMOTIONS = [
    "neutral", "happy", "sad", "angry", "fear",
    "surprise", "disgust", "excited", "calm", "confused",
    "anxious", "hopeful", "melancholy", "fearful",
]

EMOTION_SPEED_MAP = {
    "neutral":    1.0,
    "happy":      1.05,
    "sad":        0.93,
    "angry":      1.08,
    "fear":       1.06,
    "surprise":   1.07,
    "disgust":    0.97,
    "excited":    1.10,
    "calm":       0.92,
    "confused":   0.96,
    "anxious":    1.04,
    "hopeful":    1.02,
    "melancholy": 0.94,
    "fearful":    1.06,
}

EMOTION_PITCH_MAP = {
    "neutral":    0.0,
    "happy":      0.6,
    "sad":       -0.5,
    "angry":     -0.3,
    "fear":       0.4,
    "surprise":   0.7,
    "disgust":   -0.2,
    "excited":    0.8,
    "calm":       0.0,
    "confused":   0.3,
    "anxious":    0.3,
    "hopeful":    0.4,
    "melancholy":-0.4,
    "fearful":    0.4,
}

BUILTIN_SPEAKERS = {
    "EN": [
        {"id": "en-default", "display_name": "English Default", "extra_info": "Standard English voice", "lang": "EN_NEWEST", "spk_key": "en-newest"},
        {"id": "en-us", "display_name": "English (US)", "extra_info": "American English voice", "lang": "EN", "spk_key": "en-us"},
        {"id": "en-br", "display_name": "English (British)", "extra_info": "British English voice", "lang": "EN", "spk_key": "en-br"},
        {"id": "en-au", "display_name": "English (Australian)", "extra_info": "Australian English voice", "lang": "EN", "spk_key": "en-au"},
        {"id": "en-india", "display_name": "English (Indian)", "extra_info": "Indian English voice", "lang": "EN", "spk_key": "en-india"},
    ],
    "ES": [
        {"id": "es-default", "display_name": "Spanish", "extra_info": "Spanish voice", "lang": "ES", "spk_key": "es"},
    ],
    "FR": [
        {"id": "fr-default", "display_name": "French", "extra_info": "French voice", "lang": "FR", "spk_key": "fr"},
    ],
    "ZH": [
        {"id": "zh-default", "display_name": "Chinese", "extra_info": "Chinese Mandarin voice", "lang": "ZH", "spk_key": "zh"},
    ],
    "JP": [
        {"id": "jp-default", "display_name": "Japanese", "extra_info": "Japanese voice", "lang": "JP", "spk_key": "jp"},
    ],
    "KR": [
        {"id": "kr-default", "display_name": "Korean", "extra_info": "Korean voice", "lang": "KR", "spk_key": "kr"},
    ],
}

ALL_VOICES = []
VOICE_LOOKUP = {}
for lang, voices in BUILTIN_SPEAKERS.items():
    for v in voices:
        entry = {
            "id": v["id"],
            "display_name": v["display_name"],
            "extra_info": v["extra_info"],
            "voice_sample_url": None,
        }
        ALL_VOICES.append(entry)
        VOICE_LOOKUP[v["id"]] = v

tone_color_converter = None
tts_models = {}
source_ses = {}
ckpt_converter = "checkpoints_v2/converter"
base_speakers_dir = "checkpoints_v2/base_speakers/ses"


def load_models():
    global tone_color_converter, tts_models, source_ses
    from openvoice.api import ToneColorConverter
    from melo.api import TTS

    device = "cuda:0" if torch.cuda.is_available() else "cpu"

    logger.info(f"Loading ToneColorConverter on {device}...")
    tone_color_converter = ToneColorConverter(
        f"{ckpt_converter}/config.json", device=device
    )
    tone_color_converter.load_ckpt(f"{ckpt_converter}/checkpoint.pth")
    logger.info("ToneColorConverter loaded.")

    for lang in BUILTIN_SPEAKERS.keys():
        melo_lang = lang
        if lang == "JP":
            melo_lang = "JP"
        elif lang == "KR":
            melo_lang = "KR"
        logger.info(f"Loading MeloTTS model for {melo_lang}...")
        tts_models[lang] = TTS(language=melo_lang, device=device)
        logger.info(f"MeloTTS {melo_lang} loaded.")

    for lang, voices in BUILTIN_SPEAKERS.items():
        for v in voices:
            se_path = f"{base_speakers_dir}/{v['spk_key']}.pth"
            if os.path.exists(se_path):
                source_ses[v["id"]] = torch.load(se_path, map_location=device)
                logger.info(f"Loaded source SE for {v['id']} from {se_path}")
            else:
                logger.warning(f"Source SE not found: {se_path}")

    logger.info("All models loaded successfully.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_models()
    yield


app = FastAPI(title="OpenVoice V2 TTS Engine", lifespan=lifespan)


def verify_auth(request: Request):
    if not BEARER_TOKEN:
        return
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
    intensity: int = Field(default=50, ge=1, le=100)
    volume: int = Field(default=75, ge=1, le=100)
    speed_adjust: float = Field(default=0.0, ge=-5.0, le=5.0)
    pitch_adjust: float = Field(default=0.0, ge=-5.0, le=5.0)


@app.post("/GetEngineDetails")
async def get_engine_details(request: Request):
    auth_err = verify_auth(request)
    if auth_err:
        return auth_err

    return {
        "engine_id": "openvoice-v2",
        "engine_name": "OpenVoice V2",
        "sample_rate": SAMPLE_RATE,
        "bit_depth": BIT_DEPTH,
        "channels": CHANNELS,
        "max_seconds_per_conversion": MAX_SECONDS,
        "supports_voice_cloning": True,
        "builtin_voices": ALL_VOICES,
        "supported_emotions": CANONICAL_EMOTIONS,
        "extra_properties": {
            "architecture": "MeloTTS base + ToneColorConverter for voice cloning",
            "languages": ["English", "Spanish", "French", "Chinese", "Japanese", "Korean"],
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

    voice_id = req.builtin_voice_id or "en-default"
    voice_info = VOICE_LOOKUP.get(voice_id)
    if not voice_info:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"Voice '{voice_id}' not found",
                "error_code": "VOICE_NOT_FOUND",
                "details": f"Available voices: {', '.join(VOICE_LOOKUP.keys())}"
            }
        )

    if req.random_seed is not None:
        torch.manual_seed(req.random_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed(req.random_seed)

    temp_files = []

    try:
        lang_key = None
        for lk, voices in BUILTIN_SPEAKERS.items():
            if any(v["id"] == voice_info["id"] for v in voices):
                lang_key = lk
                break
        if not lang_key:
            lang_key = "EN"

        melo_model = tts_models.get(lang_key)
        if not melo_model:
            return JSONResponse(
                status_code=500,
                content={"error": f"TTS model for language {lang_key} not loaded", "error_code": "GENERATION_FAILED"}
            )

        dominant_emotion = req.emotion_set[0].lower() if req.emotion_set else "neutral"
        if dominant_emotion not in EMOTION_SPEED_MAP:
            dominant_emotion = "neutral"

        intensity_scale = req.intensity / 50.0
        emotion_speed_raw = EMOTION_SPEED_MAP[dominant_emotion]
        emotion_speed = 1.0 + (emotion_speed_raw - 1.0) * intensity_scale
        emotion_pitch_raw = EMOTION_PITCH_MAP[dominant_emotion]
        emotion_pitch = emotion_pitch_raw * intensity_scale

        speed = emotion_speed * (1.0 + (req.speed_adjust / 100.0))
        speed = max(0.5, min(2.0, speed))

        logger.info(
            f"Emotion: {dominant_emotion}, intensity: {req.intensity}, "
            f"emotion_speed: {emotion_speed:.3f}, emotion_pitch: {emotion_pitch:.2f}, "
            f"final_speed: {speed:.3f}"
        )

        spk2id = melo_model.hps.data.spk2id
        melo_lang = voice_info["lang"]

        speaker_id_value = None
        for spk_name, spk_id in spk2id.items():
            normalized = spk_name.lower().replace("_", "-")
            if normalized == voice_info["spk_key"]:
                speaker_id_value = spk_id
                break

        if speaker_id_value is None:
            logger.warning(f"Speaker key '{voice_info['spk_key']}' not found in MeloTTS model, available: {list(spk2id.keys())}")
            speaker_id_value = list(spk2id.values())[0]

        tmp_base = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_base.close()
        temp_files.append(tmp_base.name)

        melo_model.tts_to_file(
            req.input_text,
            speaker_id_value,
            tmp_base.name,
            speed=speed,
        )

        if req.voice_to_clone_sample:
            from openvoice import se_extractor

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
                    content={"error": "Voice clone sample is too small to be valid audio", "error_code": "INVALID_REQUEST"}
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
                    content={"error": "Voice clone sample is not a valid audio file", "error_code": "INVALID_REQUEST"}
                )

            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            target_se, _ = se_extractor.get_se(
                tmp_ref.name, tone_color_converter, vad=False
            )

            src_se = source_ses.get(voice_info["id"])
            if src_se is None:
                src_se = list(source_ses.values())[0] if source_ses else None

            if src_se is None:
                return JSONResponse(
                    status_code=500,
                    content={"error": "No source speaker embedding available", "error_code": "GENERATION_FAILED"}
                )

            tmp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_out.close()
            temp_files.append(tmp_out.name)

            tone_color_converter.convert(
                audio_src_path=tmp_base.name,
                src_se=src_se,
                tgt_se=target_se,
                output_path=tmp_out.name,
            )

            audio_np, file_sr = sf.read(tmp_out.name)
        else:
            audio_np, file_sr = sf.read(tmp_base.name)

        if len(audio_np.shape) > 1:
            audio_np = audio_np.mean(axis=1)
        audio_np = audio_np.astype(np.float32)

        max_val = np.max(np.abs(audio_np))
        if max_val > 0:
            audio_np = audio_np / max_val

        total_pitch = emotion_pitch + (req.pitch_adjust * 0.24)
        if total_pitch != 0.0:
            audio_np = pyrb.pitch_shift(audio_np, file_sr, total_pitch)

        vol_factor = req.volume / 75.0
        audio_np = audio_np * vol_factor

        wav_bytes = numpy_to_wav_bytes(audio_np, file_sr)

        return Response(content=wav_bytes, media_type="audio/wav")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.exception("TTS generation failed")
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Audio generation failed: {type(e).__name__}: {e}",
                "error_code": "GENERATION_FAILED",
                "traceback": tb,
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
        "converter_loaded": tone_color_converter is not None,
        "tts_models_loaded": list(tts_models.keys()),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
