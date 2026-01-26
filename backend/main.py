"""
Narrator AI - FastAPI Backend
Text to Audiobook Generator with Chatterbox TTS
"""

import os
import re
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from text_parser import TextParser
from audio_processor import AudioProcessor
from tts_service import TTSService
from models import (
    VoiceSample,
    TextSegment,
    ProjectConfig,
    ParseTextRequest,
    ParseTextResponse,
    GenerateRequest,
    GenerateResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Narrator AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
VOICES_DIR = UPLOAD_DIR / "voices"
VOICES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = UPLOAD_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
VOICE_LIBRARY_DIR = Path(__file__).parent.parent / "voice_samples"

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
if VOICE_LIBRARY_DIR.exists():
    app.mount("/voice_library", StaticFiles(directory=str(VOICE_LIBRARY_DIR)), name="voice_library")

text_parser = TextParser()
audio_processor = AudioProcessor()
tts_service = TTSService()

voice_samples: dict[str, VoiceSample] = {}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/voices")
async def get_voices():
    """Get all voice samples"""
    return list(voice_samples.values())


@app.post("/voices/upload")
async def upload_voice(
    name: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a voice sample for cloning"""
    try:
        voice_id = str(uuid.uuid4())
        file_ext = Path(file.filename).suffix if file.filename else ".wav"
        file_path = VOICES_DIR / f"{voice_id}{file_ext}"
        
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        duration = audio_processor.get_audio_duration(str(file_path))
        
        sample = VoiceSample(
            id=voice_id,
            name=name,
            audioUrl=f"/uploads/voices/{voice_id}{file_ext}",
            duration=duration,
            createdAt=str(uuid.uuid4())[:10],
        )
        voice_samples[voice_id] = sample
        
        logger.info(f"Uploaded voice sample: {name} ({duration:.1f}s)")
        return sample.model_dump()
    except Exception as e:
        logger.error(f"Failed to upload voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/voices/{voice_id}")
async def delete_voice(voice_id: str):
    """Delete a voice sample"""
    if voice_id not in voice_samples:
        raise HTTPException(status_code=404, detail="Voice not found")
    
    sample = voice_samples.pop(voice_id)
    file_path = UPLOAD_DIR / sample.audioUrl.lstrip("/uploads/")
    if file_path.exists():
        file_path.unlink()
    
    return {"success": True}


def format_location(location: str, language: str) -> str:
    """Format location for display, e.g., 'Southern_England' -> 'Southern England'
    Only add country suffix if appropriate based on language/region context."""
    formatted = location.replace("_", " ")
    
    lang_lower = language.lower()
    
    if lang_lower == "scottish":
        if "scotland" not in formatted.lower():
            formatted += ", Scotland"
    elif lang_lower == "northernirish":
        if "ireland" not in formatted.lower() and "ulster" not in formatted.lower():
            formatted += ", Northern Ireland"
    elif lang_lower == "irish":
        if "ireland" not in formatted.lower():
            formatted += ", Ireland"
    elif lang_lower == "welsh":
        if "wales" not in formatted.lower():
            formatted += ", Wales"
    elif lang_lower == "english":
        if "england" not in formatted.lower():
            formatted += ", England"
    elif lang_lower == "american":
        if "usa" not in formatted.lower() and "america" not in formatted.lower():
            formatted += ", USA"
    elif lang_lower == "canadian":
        if "canada" not in formatted.lower():
            formatted += ", Canada"
    elif lang_lower == "australian":
        if "australia" not in formatted.lower():
            formatted += ", Australia"
    elif lang_lower == "newzealand":
        if "zealand" not in formatted.lower():
            formatted += ", New Zealand"
    elif lang_lower == "southafrican":
        if "africa" not in formatted.lower():
            formatted += ", South Africa"
    elif lang_lower == "indian":
        if "india" not in formatted.lower():
            formatted += ", India"
    
    return formatted


@app.get("/voice-library")
async def get_voice_library():
    """Get all voices from the voice library"""
    if not VOICE_LIBRARY_DIR.exists():
        return []
    
    voices = []
    seen_ids = set()
    
    metadata_pattern = re.compile(r"p(\d+)_([MF])_(\d+)_([^_]+)_(.+?)(?:_nopunct)?\.txt")
    
    for txt_file in VOICE_LIBRARY_DIR.glob("*.txt"):
        if "_nopunct" in txt_file.name:
            continue
        
        match = metadata_pattern.match(txt_file.name)
        if not match:
            continue
        
        voice_num = match.group(1)
        voice_id = f"p{voice_num}"
        
        if voice_id in seen_ids:
            continue
        seen_ids.add(voice_id)
        
        gender = match.group(2)
        age = int(match.group(3))
        language = match.group(4)
        location = match.group(5)
        
        mic1_file = VOICE_LIBRARY_DIR / f"{voice_id}_mic1.wav"
        mic2_file = VOICE_LIBRARY_DIR / f"{voice_id}_mic2.wav"
        
        if not mic1_file.exists():
            continue
        
        try:
            transcript = txt_file.read_text().strip()
        except:
            transcript = None
        
        try:
            duration = audio_processor.get_audio_duration(str(mic1_file))
        except:
            duration = 0.0
        
        display_location = format_location(location, language)
        display_name = f"Voice {voice_num}: {gender}/{age} {display_location}"
        
        voices.append({
            "id": voice_id,
            "name": display_name,
            "gender": gender,
            "age": age,
            "language": language,
            "location": location,
            "audioUrl": f"/voice_library/{voice_id}_mic1.wav",
            "altAudioUrl": f"/voice_library/{voice_id}_mic2.wav" if mic2_file.exists() else None,
            "transcript": transcript,
            "duration": duration,
        })
    
    voices.sort(key=lambda v: int(v["id"][1:]))
    logger.info(f"Found {len(voices)} voices in library")
    return voices


@app.post("/parse-text")
async def parse_text(request: ParseTextRequest):
    """Parse text into segments with sentiment analysis"""
    try:
        segments, speakers = text_parser.parse(request.text)
        return ParseTextResponse(
            segments=segments,
            detectedSpeakers=speakers,
        )
    except Exception as e:
        logger.error(f"Failed to parse text: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate")
async def generate_audio(request: GenerateRequest):
    """Generate audiobook from parsed segments"""
    try:
        output_id = str(uuid.uuid4())
        output_path = OUTPUT_DIR / f"{output_id}.wav"
        
        voice_files = {}
        
        # Add uploaded voice samples
        for voice_id, sample in voice_samples.items():
            voice_files[voice_id] = str(UPLOAD_DIR / sample.audioUrl.lstrip("/uploads/"))
        
        # Add library voices (with library: prefix)
        if VOICE_LIBRARY_DIR.exists():
            for wav_file in VOICE_LIBRARY_DIR.glob("*_mic1.wav"):
                voice_id = wav_file.stem.replace("_mic1", "")  # e.g., "p226"
                voice_files[f"library:{voice_id}"] = str(wav_file)
        
        tts_service.generate_audiobook(
            segments=request.segments,
            config=request.config,
            voice_files=voice_files,
            output_path=str(output_path),
            audio_processor=audio_processor,
        )
        
        return GenerateResponse(
            audioUrl=f"/uploads/output/{output_id}.wav"
        )
    except Exception as e:
        logger.error(f"Failed to generate audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
