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
MODEL_ID = "Qwen/Qwen2.5-Omni-7B"
SAMPLE_RATE = 24000
BIT_DEPTH = 16
CHANNELS = 1
MAX_SECONDS = 30

BUILTIN_VOICES = [
    {"id": "Chelsie", "display_name": "Chelsie", "extra_info": "Default female voice, warm and clear"},
    {"id": "Ethan", "display_name": "Ethan", "extra_info": "Male voice, confident and steady"},
]

model = None
processor = None


def load_model():
    global model, processor
    from transformers import Qwen2_5OmniModel, Qwen2_5OmniProcessor

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32

    logger.info(f"Loading Qwen2.5-Omni model on {device} with dtype {dtype}...")
    model = Qwen2_5OmniModel.from_pretrained(
        MODEL_ID,
        torch_dtype=dtype,
        device_map="auto" if device == "cuda" else None,
        attn_implementation="flash_attention_2" if device == "cuda" else "sdpa",
    )
    if device != "cuda":
        model = model.to(device)

    processor = Qwen2_5OmniProcessor.from_pretrained(MODEL_ID)
    logger.info("Qwen2.5-Omni model loaded successfully.")


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


def load_audio_from_base64(b64_data: str) -> tuple[np.ndarray, int]:
    wav_bytes = base64.b64decode(b64_data)
    buf = io.BytesIO(wav_bytes)
    audio, sr = sf.read(buf)
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)
    return audio.astype(np.float32), sr


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
        "engine_name": "Qwen 2.5 Omni TTS",
        "sample_rate": SAMPLE_RATE,
        "bit_depth": BIT_DEPTH,
        "channels": CHANNELS,
        "max_seconds_per_conversion": MAX_SECONDS,
        "supports_voice_cloning": True,
        "builtin_voices": BUILTIN_VOICES,
        "supported_emotions": [
            "neutral", "happy", "sad", "angry", "fear",
            "surprise", "excited", "calm"
        ],
        "extra_properties": {
            "model": MODEL_ID,
            "languages": [
                "en", "zh", "ja", "ko", "fr", "de", "es", "it",
                "pt", "ru", "ar", "nl", "pl", "tr", "vi", "th"
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

    voice_id = req.builtin_voice_id or "Chelsie"
    known_ids = [v["id"] for v in BUILTIN_VOICES]
    if voice_id not in known_ids and not req.voice_to_clone_sample:
        return JSONResponse(
            status_code=404,
            content={
                "error": f"Voice '{voice_id}' not found",
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
        emotion_prefix = ""
        if req.emotion_set and req.emotion_set[0] != "neutral":
            dominant = req.emotion_set[0]
            intensity_word = "slightly" if req.intensity < 33 else ("very" if req.intensity > 66 else "")
            emotion_prefix = f"[{intensity_word} {dominant}] " if intensity_word else f"[{dominant}] "

        synth_text = emotion_prefix + req.input_text

        conversation = [
            {
                "role": "user",
                "content": [{"type": "text", "text": synth_text}],
            }
        ]

        if req.voice_to_clone_sample:
            clone_audio, clone_sr = load_audio_from_base64(req.voice_to_clone_sample)
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            sf.write(tmp.name, clone_audio, clone_sr)
            tmp.close()
            temp_files.append(tmp.name)

            conversation = [
                {
                    "role": "user",
                    "content": [
                        {"type": "audio", "audio": tmp.name},
                        {"type": "text", "text": f"Please speak the following text using the same voice as the audio sample: {synth_text}"},
                    ],
                }
            ]

        text = processor.apply_chat_template(conversation, add_generation_prompt=True, tokenize=False)
        audios, images, videos = processor.process_multimedia(conversation)

        inputs = processor(
            text=text,
            audios=audios,
            images=images,
            videos=videos,
            return_tensors="pt",
            padding=True,
        )
        inputs = inputs.to(model.device)

        generate_kwargs = {
            "use_audio_in_video": False,
            "max_new_tokens": 2048,
        }
        if not req.voice_to_clone_sample:
            generate_kwargs["speaker"] = voice_id

        with torch.no_grad():
            text_ids, audio_wav = model.generate(
                **inputs,
                **generate_kwargs,
            )

        if audio_wav is None:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Model did not produce audio output",
                    "error_code": "GENERATION_FAILED",
                }
            )

        if isinstance(audio_wav, torch.Tensor):
            audio_np = audio_wav.cpu().float().numpy()
        else:
            audio_np = np.array(audio_wav, dtype=np.float32)

        if len(audio_np.shape) > 1:
            audio_np = audio_np.squeeze()

        max_val = np.max(np.abs(audio_np))
        if max_val > 0:
            audio_np = audio_np / max_val

        speed = 1.0 + (req.speed_adjust / 100.0)
        speed = max(0.5, min(2.0, speed))
        if speed != 1.0:
            audio_np = pyrb.time_stretch(audio_np, SAMPLE_RATE, speed)

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
    return {"status": "ok", "model_loaded": model is not None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
