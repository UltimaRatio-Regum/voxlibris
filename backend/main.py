"""
Narrator AI - FastAPI Backend
Text to Audiobook Generator with Chatterbox TTS
"""

import os
import re
import json
import uuid
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from text_parser import TextParser
from audio_processor import AudioProcessor
from tts_service import TTSService, list_edge_voices, EDGE_TTS_VOICES, OPENAI_TTS_VOICES
from models import (
    VoiceSample,
    TextSegment,
    ProjectConfig,
    ParseTextRequest,
    ParseTextResponse,
    GenerateRequest,
    GenerateResponse,
)
from database import (
    get_db_session, TTSEngineEndpoint, VoiceLibraryEntry, CustomVoice,
    Project, ProjectChapter, ProjectSection, ProjectChunk, ProjectAudioFile
)
from remote_tts_client import RemoteTTSClient
from project_segmenter import segment_project_background, split_into_sections

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TARGET_CHUNK_WORDS = 25
MAX_CHUNK_WORDS = 30

def rechunk_segment(text: str) -> list[str]:
    """Re-chunk a segment that exceeds the target word count using smart splitting."""
    words = text.split()
    if len(words) <= MAX_CHUNK_WORDS:
        return [text]
    
    chunks: list[str] = []
    remaining = text.strip()
    
    while remaining.strip():
        word_count = len(remaining.split())
        if word_count <= MAX_CHUNK_WORDS:
            chunks.append(remaining.strip())
            break
        
        target_char_pos = _words_to_char_pos(remaining, TARGET_CHUNK_WORDS)
        split_pos = _find_best_split(remaining, target_char_pos)
        
        if split_pos <= 0 or split_pos >= len(remaining) - 1:
            split_pos = target_char_pos
            space_pos = remaining.rfind(' ', 0, split_pos + 1)
            if space_pos > 0:
                split_pos = space_pos
        
        chunk = remaining[:split_pos].strip()
        remaining = remaining[split_pos:].strip()
        
        if chunk:
            chunks.append(chunk)
    
    return chunks if chunks else [text]

def _words_to_char_pos(text: str, word_count: int) -> int:
    words = text.split()
    if word_count >= len(words):
        return len(text)
    current_word = 0
    for i, char in enumerate(text):
        if char.isspace() and i > 0 and not text[i-1].isspace():
            current_word += 1
            if current_word >= word_count:
                return i
    avg_chars = len(text) / max(1, len(words))
    return int(word_count * avg_chars)

def _find_best_split(text: str, target_pos: int) -> int:
    search_start = max(0, target_pos - 100)
    search_end = min(len(text), target_pos + 50)
    region = text[search_start:search_end]
    
    for pattern in [r'[.!?]\s+', r'[:;]\s+', r',\s+']:
        matches = list(re.finditer(pattern, region))
        if matches:
            best = max(matches, key=lambda m: m.end()) if pattern == r'[.!?]\s+' else min(matches, key=lambda m: abs(m.end() - len(region)//2))
            return search_start + best.end()
    
    conjunctions = list(re.finditer(r'\s+(and|but|or|yet|so|for|nor|because|though|while)\s+', region, re.IGNORECASE))
    if conjunctions:
        best = min(conjunctions, key=lambda m: abs(m.start() - len(region)//2))
        return search_start + best.start()
    
    spaces = list(re.finditer(r'\s+', region))
    if spaces:
        best = min(spaces, key=lambda m: abs(m.start() - len(region)//2))
        return search_start + best.start()
    
    return target_pos

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


def _load_custom_voices_from_db():
    """Load all custom voices from the database into the in-memory dict."""
    try:
        db = get_db_session()
        try:
            voices = db.query(CustomVoice).all()
            for v in voices:
                voice_samples[v.id] = VoiceSample(
                    id=v.id,
                    name=v.name,
                    audioUrl=f"/custom-voices/{v.id}/audio",
                    duration=v.duration,
                    createdAt=v.created_at.isoformat() if v.created_at else "",
                )
            logger.info(f"Loaded {len(voices)} custom voices from database")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not load custom voices from DB: {e}")


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
    """Upload a voice sample for cloning, persisted to database"""
    try:
        voice_id = str(uuid.uuid4())
        file_ext = Path(file.filename).suffix if file.filename else ".wav"
        content = await file.read()

        duration = 0.0
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=True) as tmp:
                tmp.write(content)
                tmp.flush()
                duration = audio_processor.get_audio_duration(tmp.name)
        except Exception:
            pass

        db = get_db_session()
        try:
            entry = CustomVoice(
                id=voice_id,
                name=name,
                audio_data=content,
                file_ext=file_ext,
                duration=duration,
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()

        sample = VoiceSample(
            id=voice_id,
            name=name,
            audioUrl=f"/custom-voices/{voice_id}/audio",
            duration=duration,
            createdAt=datetime.utcnow().isoformat(),
        )
        voice_samples[voice_id] = sample

        logger.info(f"Uploaded custom voice: {name} ({duration:.1f}s)")
        return sample.model_dump()
    except Exception as e:
        logger.error(f"Failed to upload voice: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/custom-voices/{voice_id}/audio")
async def get_custom_voice_audio(voice_id: str):
    """Stream custom voice audio from database"""
    db = get_db_session()
    try:
        voice = db.query(CustomVoice).filter(CustomVoice.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail="Voice not found")
        media_type = "audio/wav" if voice.file_ext in [".wav", ""] else f"audio/{voice.file_ext.lstrip('.')}"
        return Response(content=voice.audio_data, media_type=media_type)
    finally:
        db.close()


@app.get("/custom-voices")
async def list_custom_voices():
    """List all custom voices from the database"""
    db = get_db_session()
    try:
        voices = db.query(CustomVoice).order_by(CustomVoice.created_at.desc()).all()
        return [
            {
                "id": v.id,
                "name": v.name,
                "duration": v.duration,
                "audioUrl": f"/custom-voices/{v.id}/audio",
                "createdAt": v.created_at.isoformat() if v.created_at else "",
            }
            for v in voices
        ]
    finally:
        db.close()


@app.put("/custom-voices/{voice_id}")
async def rename_custom_voice(voice_id: str, name: str = Form(...)):
    """Rename a custom voice"""
    db = get_db_session()
    try:
        voice = db.query(CustomVoice).filter(CustomVoice.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail="Voice not found")
        voice.name = name
        db.commit()
        if voice_id in voice_samples:
            voice_samples[voice_id].name = name
        return {"success": True, "name": name}
    finally:
        db.close()


@app.delete("/voices/{voice_id}")
async def delete_voice(voice_id: str):
    """Delete a voice sample from database"""
    db = get_db_session()
    try:
        voice = db.query(CustomVoice).filter(CustomVoice.id == voice_id).first()
        if voice:
            db.delete(voice)
            db.commit()
        voice_samples.pop(voice_id, None)
        return {"success": True}
    finally:
        db.close()


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


class AddEngineRequest(BaseModel):
    url: str
    api_key: Optional[str] = None


@app.get("/tts-engines")
async def list_tts_engines():
    """List all registered TTS engine endpoints from the database."""
    db = get_db_session()
    try:
        engines = db.query(TTSEngineEndpoint).filter(TTSEngineEndpoint.is_active == True).all()
        result = []
        for e in engines:
            result.append({
                "id": e.id,
                "engine_id": e.engine_id,
                "engine_name": e.engine_name,
                "base_url": e.base_url,
                "has_api_key": bool(e.api_key),
                "sample_rate": e.sample_rate,
                "bit_depth": e.bit_depth,
                "channels": e.channels,
                "max_seconds_per_conversion": e.max_seconds_per_conversion,
                "supports_voice_cloning": e.supports_voice_cloning,
                "builtin_voices": json.loads(e.builtin_voices_json) if e.builtin_voices_json else [],
                "base_voices": json.loads(e.base_voices_json) if e.base_voices_json else [],
                "supported_emotions": json.loads(e.supported_emotions_json) if e.supported_emotions_json else [],
                "last_tested_at": e.last_tested_at.isoformat() if e.last_tested_at else None,
                "last_test_success": e.last_test_success,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            })
        return result
    finally:
        db.close()


@app.post("/tts-engines")
async def add_tts_engine(request: AddEngineRequest):
    """Register a new TTS engine by URL. Queries GetEngineDetails and stores in DB."""
    try:
        client = RemoteTTSClient(request.url, request.api_key)
        details = await client.get_engine_details()
    except Exception as e:
        logger.error(f"Failed to query engine at {request.url}: {e}")
        raise HTTPException(status_code=400, detail=f"Could not reach engine: {str(e)}")

    db = get_db_session()
    try:
        existing = db.query(TTSEngineEndpoint).filter(
            TTSEngineEndpoint.engine_id == details.engine_id
        ).first()
        if existing:
            existing.engine_name = details.engine_name
            existing.base_url = request.url.rstrip("/")
            existing.api_key = request.api_key
            existing.sample_rate = details.sample_rate
            existing.bit_depth = details.bit_depth
            existing.channels = details.channels
            existing.max_seconds_per_conversion = details.max_seconds_per_conversion
            existing.supports_voice_cloning = details.supports_voice_cloning
            existing.builtin_voices_json = json.dumps([
                {"id": v.id, "display_name": v.display_name, "extra_info": v.extra_info, "voice_sample_url": v.voice_sample_url}
                for v in details.builtin_voices
            ])
            existing.base_voices_json = json.dumps([
                {"id": v.id, "display_name": v.display_name, "extra_info": v.extra_info, "voice_sample_url": v.voice_sample_url}
                for v in details.base_voices
            ]) if details.base_voices else None
            existing.supported_emotions_json = json.dumps(details.supported_emotions)
            existing.extra_properties_json = json.dumps(details.extra_properties)
            existing.is_active = True
            existing.last_tested_at = datetime.utcnow()
            existing.last_test_success = True
            existing.updated_at = datetime.utcnow()
            db.commit()
            return {"status": "updated", "engine_id": details.engine_id, "engine_name": details.engine_name}
        else:
            entry = TTSEngineEndpoint(
                id=str(uuid.uuid4()),
                engine_id=details.engine_id,
                engine_name=details.engine_name,
                base_url=request.url.rstrip("/"),
                api_key=request.api_key,
                sample_rate=details.sample_rate,
                bit_depth=details.bit_depth,
                channels=details.channels,
                max_seconds_per_conversion=details.max_seconds_per_conversion,
                supports_voice_cloning=details.supports_voice_cloning,
                builtin_voices_json=json.dumps([
                    {"id": v.id, "display_name": v.display_name, "extra_info": v.extra_info, "voice_sample_url": v.voice_sample_url}
                    for v in details.builtin_voices
                ]),
                base_voices_json=json.dumps([
                    {"id": v.id, "display_name": v.display_name, "extra_info": v.extra_info, "voice_sample_url": v.voice_sample_url}
                    for v in details.base_voices
                ]) if details.base_voices else None,
                supported_emotions_json=json.dumps(details.supported_emotions),
                extra_properties_json=json.dumps(details.extra_properties),
                is_active=True,
                last_tested_at=datetime.utcnow(),
                last_test_success=True,
            )
            db.add(entry)
            db.commit()
            return {"status": "added", "engine_id": details.engine_id, "engine_name": details.engine_name}
    finally:
        db.close()


@app.post("/tts-engines/{engine_id}/test")
async def test_tts_engine(engine_id: str):
    """Test connectivity to a registered TTS engine."""
    db = get_db_session()
    try:
        entry = db.query(TTSEngineEndpoint).filter(
            TTSEngineEndpoint.engine_id == engine_id
        ).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Engine not found")

        try:
            client = RemoteTTSClient(entry.base_url, entry.api_key)
            details = await client.get_engine_details()
            entry.last_tested_at = datetime.utcnow()
            entry.last_test_success = True
            entry.engine_name = details.engine_name
            entry.builtin_voices_json = json.dumps([
                {"id": v.id, "display_name": v.display_name, "extra_info": v.extra_info, "voice_sample_url": v.voice_sample_url}
                for v in details.builtin_voices
            ])
            entry.base_voices_json = json.dumps([
                {"id": v.id, "display_name": v.display_name, "extra_info": v.extra_info, "voice_sample_url": v.voice_sample_url}
                for v in details.base_voices
            ]) if details.base_voices else None
            entry.supported_emotions_json = json.dumps(details.supported_emotions)
            entry.updated_at = datetime.utcnow()
            db.commit()
            return {"success": True, "engine_name": details.engine_name, "voices": len(details.builtin_voices)}
        except Exception as e:
            entry.last_tested_at = datetime.utcnow()
            entry.last_test_success = False
            entry.updated_at = datetime.utcnow()
            db.commit()
            return {"success": False, "error": str(e)}
    finally:
        db.close()


@app.delete("/tts-engines/{engine_id}")
async def remove_tts_engine(engine_id: str):
    """Remove a registered TTS engine."""
    db = get_db_session()
    try:
        entry = db.query(TTSEngineEndpoint).filter(
            TTSEngineEndpoint.engine_id == engine_id
        ).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Engine not found")
        db.delete(entry)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.get("/voice-library-db")
async def get_voice_library_db():
    """Get all voices from the PostgreSQL voice library."""
    db = get_db_session()
    try:
        voices = db.query(VoiceLibraryEntry).all()
        result = []
        for v in voices:
            result.append({
                "id": v.id,
                "name": v.name,
                "gender": v.gender,
                "age": v.age,
                "language": v.language,
                "location": v.location,
                "transcript": v.transcript,
                "duration": v.duration,
                "audioUrl": f"/voice-library-db/{v.id}/audio",
                "altAudioUrl": f"/voice-library-db/{v.id}/alt-audio" if v.alt_audio_data else None,
                "hasAudio": bool(v.audio_data),
                "hasAltAudio": bool(v.alt_audio_data),
            })
        result.sort(key=lambda x: x["id"])
        return result
    finally:
        db.close()


@app.get("/voice-library-db/{voice_id}/audio")
async def get_voice_audio(voice_id: str):
    """Stream voice sample audio from the database."""
    db = get_db_session()
    try:
        voice = db.query(VoiceLibraryEntry).filter(VoiceLibraryEntry.id == voice_id).first()
        if not voice or not voice.audio_data:
            raise HTTPException(status_code=404, detail="Voice audio not found")
        return Response(content=voice.audio_data, media_type="audio/wav")
    finally:
        db.close()


@app.get("/voice-library-db/{voice_id}/alt-audio")
async def get_voice_alt_audio(voice_id: str):
    """Stream alternate voice sample audio from the database."""
    db = get_db_session()
    try:
        voice = db.query(VoiceLibraryEntry).filter(VoiceLibraryEntry.id == voice_id).first()
        if not voice or not voice.alt_audio_data:
            raise HTTPException(status_code=404, detail="Alternate voice audio not found")
        return Response(content=voice.alt_audio_data, media_type="audio/wav")
    finally:
        db.close()


@app.post("/voice-library-db")
async def upload_voice_to_library(
    name: str = Form(...),
    gender: str = Form(...),
    age: int = Form(0),
    language: str = Form(""),
    location: str = Form(""),
    transcript: str = Form(""),
    file: UploadFile = File(...),
):
    """Upload a voice sample to the PostgreSQL voice library."""
    try:
        audio_bytes = await file.read()
        voice_id = f"custom_{uuid.uuid4().hex[:8]}"

        duration = 0.0
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                duration = audio_processor.get_audio_duration(tmp.name)
        except Exception:
            pass

        db = get_db_session()
        try:
            entry = VoiceLibraryEntry(
                id=voice_id,
                name=name,
                gender=gender,
                age=age,
                language=language,
                location=location,
                transcript=transcript or None,
                duration=duration,
                audio_data=audio_bytes,
            )
            db.add(entry)
            db.commit()
            return {
                "id": voice_id,
                "name": name,
                "gender": gender,
                "duration": duration,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to upload voice to library: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/voice-library-db/{voice_id}")
async def delete_voice_from_library(voice_id: str):
    """Delete a voice from the PostgreSQL voice library."""
    db = get_db_session()
    try:
        voice = db.query(VoiceLibraryEntry).filter(VoiceLibraryEntry.id == voice_id).first()
        if not voice:
            raise HTTPException(status_code=404, detail="Voice not found")
        db.delete(voice)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.get("/edge-voices")
async def get_edge_voices():
    """Get all available edge-tts voices"""
    try:
        voices = await list_edge_voices()
        return {
            "voices": voices,
            "presets": EDGE_TTS_VOICES,
        }
    except Exception as e:
        logger.error(f"Failed to list edge-tts voices: {e}")
        return {"voices": [], "presets": EDGE_TTS_VOICES}


@app.get("/openai-voices")
async def get_openai_voices():
    """Get available OpenAI TTS voices"""
    return {
        "voices": [
            {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced voice"},
            {"id": "echo", "name": "Echo", "description": "Male, warm tone"},
            {"id": "fable", "name": "Fable", "description": "British accent"},
            {"id": "onyx", "name": "Onyx", "description": "Deep, authoritative"},
            {"id": "nova", "name": "Nova", "description": "Female, energetic"},
            {"id": "shimmer", "name": "Shimmer", "description": "Female, soft"},
        ],
        "presets": OPENAI_TTS_VOICES,
    }


@app.get("/chatterbox-status")
async def get_chatterbox_status():
    """Get Chatterbox TTS configuration status"""
    from chatterbox_config import is_paid_chatterbox_configured, CHATTERBOX_PAID_CONFIG, CHATTERBOX_FREE_CONFIG
    
    return {
        "free": {
            "available": True,
            "space_id": CHATTERBOX_FREE_CONFIG["space_id"],
            "max_chars": CHATTERBOX_FREE_CONFIG["max_chars"],
        },
        "paid": {
            "configured": is_paid_chatterbox_configured(),
            "space_url": CHATTERBOX_PAID_CONFIG["space_url"],
            "api_key_set": bool(CHATTERBOX_PAID_CONFIG["api_key"]),
            "max_chars": CHATTERBOX_PAID_CONFIG["max_chars"],
        },
    }


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


class ParseTextLLMRequest(BaseModel):
    text: str
    model: str = "openai/gpt-4o-mini"
    knownSpeakers: list[str] = []


@app.post("/parse-text-llm-stream")
async def parse_text_llm_stream(request: ParseTextLLMRequest):
    """Parse text using LLM with streaming progress updates via SSE"""
    from starlette.responses import StreamingResponse
    import json
    import httpx
    import asyncio
    
    OPENROUTER_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")
    
    def split_into_chunks(text: str, max_paragraphs: int = 3) -> list[str]:
        """Split text into chunks of ~2-3 paragraphs, respecting quote boundaries."""
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        if not paragraphs:
            return [text] if text.strip() else []
        
        chunks = []
        current_chunk = []
        straight_quote_open = False
        curly_quote_balance = 0
        
        for para in paragraphs:
            straight_quotes = para.count('"')
            curly_open = para.count('\u201c')
            curly_close = para.count('\u201d')
            
            if straight_quotes % 2 == 1:
                straight_quote_open = not straight_quote_open
            curly_quote_balance += curly_open - curly_close
            
            current_chunk.append(para)
            
            quotes_balanced = (not straight_quote_open) and (curly_quote_balance == 0)
            
            if len(current_chunk) >= max_paragraphs and quotes_balanced:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                straight_quote_open = False
                curly_quote_balance = 0
            elif len(current_chunk) >= max_paragraphs * 2:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                straight_quote_open = False
                curly_quote_balance = 0
        
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks
    
    def fallback_parse_chunk(chunk: str, known_speakers: list[str] | None = None) -> dict:
        """Use basic text parser as fallback when LLM fails."""
        segments_list, speakers_list = text_parser.parse(chunk, known_speakers=known_speakers)
        segments = []
        for seg in segments_list:
            segments.append({
                "type": seg.type,
                "text": seg.text,
                "speaker": seg.speaker,
                "emotion": seg.sentiment.label if seg.sentiment else "neutral",
                "sentiment": seg.sentiment.label if seg.sentiment else "neutral",
            })
        return {"segments": segments, "detectedSpeakers": speakers_list, "fallback": True}
    
    CANONICAL_EMOTIONS = [
        "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
        "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
    ]

    def validate_llm_response(data: dict) -> bool:
        """Validate LLM response has required structure."""
        if not isinstance(data, dict):
            return False
        if "segments" not in data or not isinstance(data.get("segments"), list):
            return False
        for seg in data["segments"]:
            if not isinstance(seg, dict):
                return False
            if "type" not in seg or "text" not in seg:
                return False
            if seg["type"] not in ["narration", "dialogue"]:
                return False
        return True
    
    async def call_llm_for_chunk(client: httpx.AsyncClient, chunk: str, known_speakers: list[str], context: str) -> dict:
        """Call LLM to segment and chunk text in one pass."""
        speaker_hint = ""
        if known_speakers:
            speaker_hint = f"\nKnown speakers from previous sections: {', '.join(known_speakers)}. Use these names when you recognize the same characters.\n"
        
        prompt = f"""You are chunking text for a text-to-speech audiobook engine. Each chunk will be sent to a TTS engine as a separate audio clip, so chunk size directly controls audio segment length.

TARGET: Each chunk must be 20-30 words (8-12 seconds of speech at 2.5 words/second). This is critical — TTS engines produce poor quality on long inputs.

CHUNKING RULES (in priority order):
1. QUOTE BOUNDARIES: Quoted dialogue must always be its own chunk, separate from surrounding narration. Never mix dialogue and narration in one chunk.
2. SIZE LIMIT: No chunk may exceed 30 words. If a sentence or paragraph is longer than 30 words, you MUST split it at a natural pause point:
   - First preference: sentence boundaries (periods, question marks, exclamation marks)
   - Second preference: semicolons, colons, or em-dashes
   - Third preference: commas or conjunctions (and, but, or, so, yet, because, though, while)
3. MINIMUM SIZE: Avoid chunks under 10 words unless they are short dialogue (e.g. "Yes," he said).
4. TYPE: Each chunk is either "narration" or "dialogue", never both.
5. SPEAKER: For dialogue, identify the speaker by name from context. For narration, speaker is null.
6. EMOTION: Assign exactly one emotion per chunk from: {CANONICAL_EMOTIONS}
7. PRESERVE TEXT: Copy the original text exactly — do not paraphrase, summarize, or omit any words.

EXAMPLE — given this input:
"She walked through the crowded marketplace, scanning the stalls for anything useful. The smell of fresh bread drifted from a nearby bakery, mixing with the sharp tang of fish from the harbor. \\"Looking for something specific?\\" the old merchant asked, leaning forward with a knowing smile."

Correct output (3 chunks, not 1):
- "She walked through the crowded marketplace, scanning the stalls for anything useful." (13 words, narration)
- "The smell of fresh bread drifted from a nearby bakery, mixing with the sharp tang of fish from the harbor." (20 words, narration)
- "Looking for something specific?" (4 words, dialogue, speaker: merchant)
{speaker_hint}
Previous context: {context[:500] if context else 'Start of text'}

TEXT TO ANALYZE:
{chunk}

Return ONLY a JSON object:
{{
  "segments": [
    {{
      "type": "narration" or "dialogue",
      "text": "exact text from the passage",
      "speaker": "speaker name or null for narration",
      "emotion": "one emotion from the list above"
    }}
  ],
  "detectedSpeakers": ["list", "of", "speaker", "names"]
}}

Return ONLY valid JSON, no markdown fences."""

        try:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": request.model,
                    "messages": [
                        {"role": "system", "content": "You are a text analysis assistant. Always respond with valid JSON only."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4096,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content.strip())
            
            if not validate_llm_response(result):
                logger.warning(f"LLM response failed validation, using fallback parser")
                return fallback_parse_chunk(chunk, known_speakers=known_speakers)
            
            if not result.get("segments"):
                logger.warning(f"LLM returned empty segments, using fallback parser")
                return fallback_parse_chunk(chunk, known_speakers=known_speakers)
            
            return result
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}")
            return fallback_parse_chunk(chunk, known_speakers=known_speakers)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return fallback_parse_chunk(chunk, known_speakers=known_speakers)
    
    async def generate_stream():
        chunks = split_into_chunks(request.text)
        total_chunks = len(chunks)
        
        if total_chunks == 0:
            yield f"data: {json.dumps({'type': 'error', 'error': 'No text to parse'})}\n\n"
            return
        
        yield f"data: {json.dumps({'type': 'progress', 'totalChunks': total_chunks, 'chunkIndex': 0})}\n\n"
        
        all_segments = []
        all_speakers = set(request.knownSpeakers)
        context = ""
        
        async with httpx.AsyncClient() as client:
            for i, chunk in enumerate(chunks):
                try:
                    result = await call_llm_for_chunk(
                        client, chunk, list(all_speakers), context
                    )
                    
                    chunk_segments = []
                    for seg in result.get("segments", []):
                        seg_text = seg.get("text", "")
                        emotion = seg.get("emotion", seg.get("sentiment", "neutral"))
                        if emotion not in CANONICAL_EMOTIONS:
                            emotion = "neutral"
                        
                        sub_texts = rechunk_segment(seg_text)
                        
                        for st in sub_texts:
                            wc = len(st.split())
                            segment = {
                                "id": str(uuid.uuid4()),
                                "type": seg.get("type", "narration"),
                                "text": st,
                                "speaker": seg.get("speaker"),
                                "speakerCandidates": {seg.get("speaker"): 0.9} if seg.get("speaker") else None,
                                "needsReview": False,
                                "sentiment": {"label": emotion, "score": 0.8},
                                "startIndex": 0,
                                "endIndex": len(st),
                                "wordCount": wc,
                                "approxDurationSeconds": round(wc / 2.5, 1),
                            }
                            chunk_segments.append(segment)
                            all_segments.append(segment)
                    
                    for speaker in result.get("detectedSpeakers", []):
                        if speaker:
                            all_speakers.add(speaker)
                    
                    context = chunk[-500:] if len(chunk) > 500 else chunk
                    
                    yield f"data: {json.dumps({'type': 'chunk', 'chunkIndex': i + 1, 'totalChunks': total_chunks, 'segments': chunk_segments, 'detectedSpeakers': list(all_speakers)})}\n\n"
                    
                except Exception as e:
                    logger.error(f"Failed to process chunk {i}: {e}")
                    yield f"data: {json.dumps({'type': 'chunk', 'chunkIndex': i + 1, 'totalChunks': total_chunks, 'segments': [], 'detectedSpeakers': list(all_speakers), 'error': str(e)})}\n\n"
        
        yield f"data: {json.dumps({'type': 'complete', 'totalSegments': len(all_segments), 'detectedSpeakers': list(all_speakers)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/parse-text-llm")
async def parse_text_llm(request: ParseTextLLMRequest):
    """Parse text using LLM (non-streaming fallback)"""
    import httpx
    
    OPENROUTER_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")
    
    CANONICAL_EMOTIONS = [
        "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
        "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
    ]
    
    speaker_hint = ""
    if request.knownSpeakers:
        speaker_hint = f"\nKnown speakers: {', '.join(request.knownSpeakers)}. Use these names when you recognize the same characters.\n"
    
    prompt = f"""You are chunking text for a text-to-speech audiobook engine. Each chunk will be sent to a TTS engine as a separate audio clip, so chunk size directly controls audio segment length.

TARGET: Each chunk must be 20-30 words (8-12 seconds of speech at 2.5 words/second). This is critical — TTS engines produce poor quality on long inputs.

CHUNKING RULES (in priority order):
1. QUOTE BOUNDARIES: Quoted dialogue must always be its own chunk, separate from surrounding narration. Never mix dialogue and narration in one chunk.
2. SIZE LIMIT: No chunk may exceed 30 words. If a sentence or paragraph is longer than 30 words, you MUST split it at a natural pause point:
   - First preference: sentence boundaries (periods, question marks, exclamation marks)
   - Second preference: semicolons, colons, or em-dashes
   - Third preference: commas or conjunctions (and, but, or, so, yet, because, though, while)
3. MINIMUM SIZE: Avoid chunks under 10 words unless they are short dialogue (e.g. "Yes," he said).
4. TYPE: Each chunk is either "narration" or "dialogue", never both.
5. SPEAKER: For dialogue, identify the speaker by name from context. For narration, speaker is null.
6. EMOTION: Assign exactly one emotion per chunk from: {CANONICAL_EMOTIONS}
7. PRESERVE TEXT: Copy the original text exactly — do not paraphrase, summarize, or omit any words.

EXAMPLE — given this input:
"She walked through the crowded marketplace, scanning the stalls for anything useful. The smell of fresh bread drifted from a nearby bakery, mixing with the sharp tang of fish from the harbor. \\"Looking for something specific?\\" the old merchant asked, leaning forward with a knowing smile."

Correct output (3 chunks, not 1):
- "She walked through the crowded marketplace, scanning the stalls for anything useful." (13 words, narration)
- "The smell of fresh bread drifted from a nearby bakery, mixing with the sharp tang of fish from the harbor." (20 words, narration)
- "Looking for something specific?" (4 words, dialogue, speaker: merchant)
{speaker_hint}
TEXT TO ANALYZE:
{request.text[:8000]}

Return ONLY a JSON object:
{{
  "segments": [
    {{"type": "narration" or "dialogue", "text": "exact text from the passage", "speaker": "name or null", "emotion": "one emotion from the list above"}}
  ],
  "detectedSpeakers": ["list", "of", "names"]
}}

Return ONLY valid JSON, no markdown fences."""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": request.model,
                    "messages": [
                        {"role": "system", "content": "You are a text analysis assistant. Always respond with valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 8192,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            result = json.loads(content.strip())
            
            segments = []
            for seg in result.get("segments", []):
                seg_text = seg.get("text", "")
                emotion = seg.get("emotion", seg.get("sentiment", "neutral"))
                if emotion not in CANONICAL_EMOTIONS:
                    emotion = "neutral"
                
                sub_texts = rechunk_segment(seg_text)
                for st in sub_texts:
                    wc = len(st.split())
                    segments.append({
                        "id": str(uuid.uuid4()),
                        "type": seg.get("type", "narration"),
                        "text": st,
                        "speaker": seg.get("speaker"),
                        "speakerCandidates": {seg.get("speaker"): 0.9} if seg.get("speaker") else None,
                        "needsReview": False,
                        "sentiment": {"label": emotion, "score": 0.8},
                        "startIndex": 0,
                        "endIndex": len(st),
                        "wordCount": wc,
                        "approxDurationSeconds": round(wc / 2.5, 1),
                    })
            
            return {
                "segments": segments,
                "detectedSpeakers": result.get("detectedSpeakers", []),
            }
    except Exception as e:
        logger.error(f"LLM parse failed: {e}")
        segments, speakers = text_parser.parse(request.text)
        return ParseTextResponse(segments=segments, detectedSpeakers=speakers)


def _resolve_voice_files() -> dict[str, str]:
    """Resolve all voice files: custom voices from DB (written to temp files),
    library voices from filesystem, and DB voice library entries."""
    import tempfile
    voice_files = {}

    db = get_db_session()
    try:
        custom = db.query(CustomVoice).all()
        for v in custom:
            tmp = tempfile.NamedTemporaryFile(suffix=v.file_ext or ".wav", delete=False)
            tmp.write(v.audio_data)
            tmp.flush()
            tmp.close()
            voice_files[v.id] = tmp.name

        db_voices = db.query(VoiceLibraryEntry).all()
        for v in db_voices:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(v.audio_data)
            tmp.flush()
            tmp.close()
            voice_files[f"library:{v.id}"] = tmp.name
    finally:
        db.close()

    if VOICE_LIBRARY_DIR.exists():
        for wav_file in VOICE_LIBRARY_DIR.glob("*_mic1.wav"):
            vid = wav_file.stem.replace("_mic1", "")
            key = f"library:{vid}"
            if key not in voice_files:
                voice_files[key] = str(wav_file)

    return voice_files


@app.post("/generate")
async def generate_audio(request: GenerateRequest):
    """Generate audiobook from parsed segments"""
    try:
        output_id = str(uuid.uuid4())
        output_path = OUTPUT_DIR / f"{output_id}.wav"

        voice_files = _resolve_voice_files()

        await tts_service.generate_audiobook_async(
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


@app.post("/generate-stream")
async def generate_audio_stream(request: GenerateRequest):
    """Generate audiobook with streaming progress updates via SSE"""
    from starlette.responses import StreamingResponse
    import json
    import asyncio
    
    # Use asyncio.Queue for real-time progress updates
    progress_queue: asyncio.Queue = asyncio.Queue()
    
    async def generate_audio_task():
        try:
            output_id = str(uuid.uuid4())
            output_path = OUTPUT_DIR / f"{output_id}.wav"
            
            voice_files = _resolve_voice_files()

            # Progress callback that puts events in queue
            def progress_callback(current: int, total: int, message: str):
                asyncio.get_event_loop().call_soon_threadsafe(
                    progress_queue.put_nowait,
                    {
                        'type': 'progress',
                        'current': current + 1,
                        'total': total,
                        'percent': int((current + 1) / total * 100),
                        'message': message
                    }
                )
            
            # Generate audio with progress tracking
            await tts_service.generate_audiobook_async(
                segments=request.segments,
                config=request.config,
                voice_files=voice_files,
                output_path=str(output_path),
                audio_processor=audio_processor,
                progress_callback=progress_callback,
            )
            
            # Signal completion
            await progress_queue.put({
                'type': 'complete', 
                'audioUrl': f'/uploads/output/{output_id}.wav'
            })
            
        except Exception as e:
            logger.error(f"Stream generation error: {e}")
            await progress_queue.put({'type': 'error', 'error': str(e)})
    
    async def generate_with_progress():
        total_segments = len(request.segments)
        
        # Send initial progress
        yield f"data: {json.dumps({'type': 'start', 'total': total_segments})}\n\n"
        
        # Start generation task
        task = asyncio.create_task(generate_audio_task())
        
        # Stream progress events as they come in
        while True:
            try:
                event = await asyncio.wait_for(progress_queue.get(), timeout=600.0)
                yield f"data: {json.dumps(event)}\n\n"
                
                if event.get('type') in ('complete', 'error'):
                    break
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'error', 'error': 'Generation timeout'})}\n\n"
                break
        
        # Wait for task to complete
        await task
    
    return StreamingResponse(
        generate_with_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


from database import init_database
from job_manager import (
    create_job, get_job, get_all_jobs, get_job_segments, 
    get_segment_audio, cancel_job, delete_job, run_cleanup_loop
)
from job_runner import start_job_async

init_database()


@app.on_event("startup")
async def startup_event():
    """Run cleanup loop on startup and load custom voices."""
    import asyncio
    _load_custom_voices_from_db()
    asyncio.create_task(run_cleanup_loop())


class CreateJobRequest(BaseModel):
    title: str = "Untitled"
    segments: list
    config: dict


@app.post("/jobs")
async def create_tts_job(request: CreateJobRequest):
    """Create a new TTS generation job."""
    try:
        job_id = create_job(
            title=request.title,
            segments=request.segments,
            config=request.config,
        )
        
        start_job_async(job_id)
        
        return {"jobId": job_id, "status": "pending"}
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs")
async def list_jobs(include_completed: bool = True, limit: int = 50):
    """List all TTS jobs."""
    try:
        jobs = get_all_jobs(include_completed=include_completed, limit=limit)
        return {"jobs": jobs}
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a TTS job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/segments")
async def get_job_segments_endpoint(job_id: str, completed_only: bool = False):
    """Get segments for a job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    segments = get_job_segments(job_id, completed_only=completed_only)
    return {"segments": segments}


@app.get("/jobs/{job_id}/segments/{segment_id}/audio")
async def get_segment_audio_endpoint(job_id: str, segment_id: str):
    """Get audio for a specific segment."""
    from fastapi.responses import Response
    
    audio_data = get_segment_audio(segment_id)
    if not audio_data:
        raise HTTPException(status_code=404, detail="Audio not found")
    
    return Response(
        content=audio_data,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"inline; filename=segment_{segment_id}.mp3"}
    )


@app.post("/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: str):
    """Cancel a running job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    cancel_job(job_id)
    return {"status": "cancelled"}


@app.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: str):
    """Delete a job and its segments."""
    if delete_job(job_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/jobs/{job_id}/audio")
async def get_combined_audio(job_id: str, max_silence_ms: int = 300):
    """Get combined audio for all completed segments with silence compression."""
    from fastapi.responses import Response
    from pydub import AudioSegment as PydubSegment
    import io
    import numpy as np
    
    max_silence_ms = max(0, min(max_silence_ms, 5000))
    
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    segments = get_job_segments(job_id, completed_only=True)
    if not segments:
        raise HTTPException(status_code=404, detail="No completed segments")
    
    combined = PydubSegment.empty()
    pause_duration = max(50, min(max_silence_ms, 200))
    pause = PydubSegment.silent(duration=pause_duration)
    
    for seg in sorted(segments, key=lambda s: s["segmentIndex"]):
        audio_data = get_segment_audio(seg["id"])
        if audio_data:
            segment_audio = PydubSegment.from_file(io.BytesIO(audio_data), format="mp3")
            combined += segment_audio + pause
    
    if len(combined) > 0 and max_silence_ms > 0:
        sample_rate = combined.frame_rate
        samples = np.array(combined.get_array_of_samples()).astype(np.float32)
        samples = samples / 32768.0
        
        from audio_processor import AudioProcessor
        processor = AudioProcessor()
        compressed = processor.compress_silence_gaps(
            samples,
            sample_rate,
            max_silence_ms=max_silence_ms,
            block_ms=25,
            silence_threshold=0.01,
        )
        
        compressed_int16 = (compressed * 32767).astype(np.int16)
        combined = PydubSegment(
            compressed_int16.tobytes(),
            frame_rate=sample_rate,
            sample_width=2,
            channels=combined.channels
        )
    
    buffer = io.BytesIO()
    combined.export(buffer, format="mp3", bitrate="192k")
    
    return Response(
        content=buffer.getvalue(),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"attachment; filename=audiobook_{job_id}.mp3"}
    )


from upload_manager import upload_manager


class StartAnalysisRequest(BaseModel):
    pass


@app.post("/uploads")
async def upload_file(
    file: UploadFile = File(...),
    tts_engine: str = Form("edge-tts"),
):
    """Upload a .txt or .epub file for processing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    ext = file.filename.lower().split('.')[-1]
    if ext not in ('txt', 'epub'):
        raise HTTPException(status_code=400, detail="Only .txt and .epub files are supported")
    
    try:
        content = await file.read()
        upload = upload_manager.create_upload(
            filename=file.filename,
            file_content=content,
            tts_engine=tts_engine
        )
        
        return {
            "uploadId": upload.id,
            "filename": upload.filename,
            "filetype": upload.filetype,
            "totalChapters": upload.total_chapters,
            "status": upload.status
        }
    except Exception as e:
        logger.error(f"Failed to process upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/uploads/{upload_id}/analyze")
async def start_analysis(upload_id: str):
    """Start background analysis for an upload."""
    upload = upload_manager.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    upload_manager.start_analysis(
        upload_id
    )
    
    return {"status": "analyzing", "uploadId": upload_id}


@app.get("/uploads")
async def list_uploads(limit: int = 20):
    """List recent uploads."""
    uploads = upload_manager.list_uploads(limit=limit)
    return {"uploads": uploads}


@app.get("/uploads/{upload_id}")
async def get_upload(upload_id: str):
    """Get upload status and chapters."""
    upload = upload_manager.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


@app.get("/uploads/{upload_id}/chapters/{chapter_id}/analysis")
async def get_chapter_analysis(upload_id: str, chapter_id: str):
    """Get analysis results for a specific chapter."""
    analysis = upload_manager.get_chapter_analysis(chapter_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@app.delete("/uploads/{upload_id}")
async def delete_upload(upload_id: str):
    """Delete an upload and all its chapters."""
    success = upload_manager.delete_upload(upload_id)
    if not success:
        raise HTTPException(status_code=404, detail="Upload not found")
    return {"status": "deleted"}


class GenerateFromUploadRequest(BaseModel):
    voiceAssignments: dict = {}
    singleVoice: Optional[str] = None
    chapterIds: Optional[list] = None


def parse_voice_id(voice_id: str) -> dict:
    """Parse voice ID string into component parts for config."""
    if voice_id.startswith("edge:"):
        return {"type": "edge", "id": voice_id[5:]}
    elif voice_id.startswith("openai:"):
        return {"type": "openai", "id": voice_id[7:]}
    elif voice_id.startswith("library:"):
        return {"type": "library", "id": voice_id[8:]}
    else:
        return {"type": "unknown", "id": voice_id}


@app.post("/uploads/{upload_id}/generate")
async def generate_from_upload(upload_id: str, request: GenerateFromUploadRequest):
    """Generate TTS jobs from an analyzed upload."""
    upload = upload_manager.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    if upload["status"] != "analyzed":
        raise HTTPException(status_code=400, detail="Upload must be analyzed before generating")
    
    job_ids = []
    
    for chapter in upload["chapters"]:
        if request.chapterIds and chapter["id"] not in request.chapterIds:
            continue
        
        if not chapter["hasAnalysis"]:
            continue
        
        analysis = upload_manager.get_chapter_analysis(chapter["id"])
        if not analysis:
            continue
        
        segments = analysis.get("segments", [])
        if not segments:
            continue
        
        speaker_configs = {}
        narrator_voice = None
        
        if request.voiceAssignments:
            for speaker, voice_id in request.voiceAssignments.items():
                parsed = parse_voice_id(voice_id)
                speaker_configs[speaker] = {
                    "name": speaker,
                    "voiceSampleId": parsed["id"],
                    "voiceType": parsed["type"],
                    "pitchOffset": 0,
                    "speedFactor": 1.0
                }
                if speaker == "Narrator":
                    narrator_voice = parsed["id"]
        
        if request.singleVoice:
            parsed_narrator = parse_voice_id(request.singleVoice)
            narrator_voice = parsed_narrator["id"]
        
        if not narrator_voice:
            raise HTTPException(
                status_code=400,
                detail="Narrator voice is required. Please select a voice for narration."
            )
        
        config = {
            "ttsEngine": upload["ttsEngine"],
            "narratorVoiceId": narrator_voice,
            "speakers": speaker_configs,
            "pauseBetweenSegments": 500,
            "defaultExaggeration": 0.5
        }
        
        job_id = create_job(
            title=f"{upload['filename']} - {chapter['title']}",
            segments=segments,
            config=config
        )
        
        from database import get_db_session, FileChapter
        db = get_db_session()
        try:
            ch = db.query(FileChapter).filter(FileChapter.id == chapter["id"]).first()
            if ch:
                ch.tts_job_id = job_id
                db.commit()
        finally:
            db.close()
        
        start_job_async(job_id)
        job_ids.append(job_id)
    
    return {"jobIds": job_ids, "count": len(job_ids)}


import json
PROSODY_SETTINGS_FILE = Path("prosody_settings.json")


def load_prosody_settings():
    """Load prosody settings from file if it exists."""
    if PROSODY_SETTINGS_FILE.exists():
        try:
            with open(PROSODY_SETTINGS_FILE, "r") as f:
                data = json.load(f)
            for emotion in AudioProcessor.VALID_EMOTIONS:
                if "pitch" in data and emotion in data["pitch"]:
                    AudioProcessor.EMOTION_PITCH_MAP[emotion] = float(data["pitch"][emotion])
                if "speed" in data and emotion in data["speed"]:
                    AudioProcessor.EMOTION_SPEED_MAP[emotion] = float(data["speed"][emotion])
                if "volume" in data and emotion in data["volume"]:
                    AudioProcessor.EMOTION_VOLUME_MAP[emotion] = float(data["volume"][emotion])
                if "intensity" in data and emotion in data["intensity"]:
                    AudioProcessor.EMOTION_INTENSITY_MAP[emotion] = float(data["intensity"][emotion])
            logger.info("Loaded prosody settings from file")
        except Exception as e:
            logger.warning(f"Failed to load prosody settings: {e}")


def save_prosody_settings():
    """Save prosody settings to file."""
    data = {
        "pitch": AudioProcessor.EMOTION_PITCH_MAP.copy(),
        "speed": AudioProcessor.EMOTION_SPEED_MAP.copy(),
        "volume": AudioProcessor.EMOTION_VOLUME_MAP.copy(),
        "intensity": AudioProcessor.EMOTION_INTENSITY_MAP.copy(),
    }
    try:
        with open(PROSODY_SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved prosody settings to file")
    except Exception as e:
        logger.warning(f"Failed to save prosody settings: {e}")


load_prosody_settings()


@app.get("/prosody-settings")
async def get_prosody_settings():
    """Get the current emotion prosody settings (pitch, speed, volume, intensity)."""
    return {
        "pitch": AudioProcessor.EMOTION_PITCH_MAP.copy(),
        "speed": AudioProcessor.EMOTION_SPEED_MAP.copy(),
        "volume": AudioProcessor.EMOTION_VOLUME_MAP.copy(),
        "intensity": AudioProcessor.EMOTION_INTENSITY_MAP.copy(),
        "emotions": AudioProcessor.VALID_EMOTIONS,
    }


class ProsodySettingsRequest(BaseModel):
    pitch: dict
    speed: dict
    volume: dict
    intensity: dict = {}


@app.post("/prosody-settings")
async def update_prosody_settings(request: ProsodySettingsRequest):
    """Update the emotion prosody settings with validation."""
    for emotion in AudioProcessor.VALID_EMOTIONS:
        if emotion in request.pitch:
            val = float(request.pitch[emotion])
            AudioProcessor.EMOTION_PITCH_MAP[emotion] = max(-12, min(12, val))
        if emotion in request.speed:
            val = float(request.speed[emotion])
            AudioProcessor.EMOTION_SPEED_MAP[emotion] = max(0.5, min(2.0, val))
        if emotion in request.volume:
            val = float(request.volume[emotion])
            AudioProcessor.EMOTION_VOLUME_MAP[emotion] = max(0.3, min(2.0, val))
        if emotion in request.intensity:
            val = float(request.intensity[emotion])
            AudioProcessor.EMOTION_INTENSITY_MAP[emotion] = max(0.0, min(1.0, val))
    
    save_prosody_settings()
    
    return {
        "success": True,
        "pitch": AudioProcessor.EMOTION_PITCH_MAP.copy(),
        "speed": AudioProcessor.EMOTION_SPEED_MAP.copy(),
        "volume": AudioProcessor.EMOTION_VOLUME_MAP.copy(),
        "intensity": AudioProcessor.EMOTION_INTENSITY_MAP.copy(),
    }


PARSING_PROMPT_FILE = Path("parsing_prompt_settings.json")


@app.get("/parsing-prompt")
async def get_parsing_prompt():
    """Get the current custom parsing/speaker-identification prompt, or indicate default is in use."""
    if PARSING_PROMPT_FILE.exists():
        try:
            with open(PARSING_PROMPT_FILE, "r") as f:
                data = json.load(f)
            if data.get("prompt"):
                return {"prompt": data["prompt"], "isCustom": True}
        except Exception as e:
            logger.warning(f"Failed to load parsing prompt: {e}")
    return {"prompt": "", "isCustom": False}


class ParsingPromptRequest(BaseModel):
    prompt: str


@app.post("/parsing-prompt")
async def update_parsing_prompt(request: ParsingPromptRequest):
    """Save a custom parsing/speaker-identification prompt."""
    try:
        with open(PARSING_PROMPT_FILE, "w") as f:
            json.dump({"prompt": request.prompt}, f, indent=2)
        logger.info("Saved custom parsing prompt to file")
        return {"success": True, "isCustom": bool(request.prompt)}
    except Exception as e:
        logger.error(f"Failed to save parsing prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/parsing-prompt")
async def reset_parsing_prompt():
    """Reset to the default parsing prompt by removing the custom file."""
    try:
        if PARSING_PROMPT_FILE.exists():
            PARSING_PROMPT_FILE.unlink()
        logger.info("Reset parsing prompt to default")
        return {"success": True, "isCustom": False}
    except Exception as e:
        logger.error(f"Failed to reset parsing prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


TTS_SETTINGS_FILE = Path(__file__).parent.parent / "tts_settings.json"

def load_tts_settings():
    """Load TTS settings from file."""
    import json
    defaults = {
        "chatterbox_model": "qwen3",
        "st_alpha": 0.3,
        "st_beta": 0.7,
        "st_diffusion_steps": 5,
        "st_embedding_scale": 1.0,
    }
    if TTS_SETTINGS_FILE.exists():
        try:
            with open(TTS_SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception as e:
            logger.warning(f"Failed to load TTS settings: {e}")
    return defaults

def save_tts_settings(settings: dict):
    """Save TTS settings to file."""
    import json
    try:
        with open(TTS_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save TTS settings: {e}")


class TTSSettingsRequest(BaseModel):
    chatterbox_model: str = "qwen3"
    st_alpha: float = 0.3
    st_beta: float = 0.7
    st_diffusion_steps: int = 5
    st_embedding_scale: float = 1.0


@app.get("/tts-settings")
async def get_tts_settings():
    """Get the current TTS model settings."""
    return load_tts_settings()


@app.post("/tts-settings")
async def update_tts_settings(request: TTSSettingsRequest):
    """Update the TTS model settings."""
    settings = {
        "chatterbox_model": request.chatterbox_model,
        "st_alpha": max(0, min(1, request.st_alpha)),
        "st_beta": max(0, min(1, request.st_beta)),
        "st_diffusion_steps": max(1, min(20, request.st_diffusion_steps)),
        "st_embedding_scale": max(0.5, min(2, request.st_embedding_scale)),
    }
    save_tts_settings(settings)
    return {"success": True, **settings}


class CreateProjectRequest(BaseModel):
    title: str
    text: Optional[str] = None


class UpdateProjectSettingsRequest(BaseModel):
    ttsEngine: Optional[str] = None
    narratorVoiceId: Optional[str] = None
    baseVoiceId: Optional[str] = None
    exaggeration: Optional[float] = None
    pauseDuration: Optional[float] = None
    speakersJson: Optional[str] = None
    outputFormat: Optional[str] = None
    metaAuthor: Optional[str] = None
    metaNarrator: Optional[str] = None
    metaGenre: Optional[str] = None
    metaYear: Optional[str] = None
    metaDescription: Optional[str] = None


class UpdateChapterRequest(BaseModel):
    ttsEngine: Optional[str] = None
    narratorVoiceId: Optional[str] = None
    speakersJson: Optional[str] = None


class UpdateChunkRequest(BaseModel):
    speakerOverride: Optional[str] = None
    emotionOverride: Optional[str] = None


class GenerateProjectAudioRequest(BaseModel):
    scopeType: str
    scopeId: str


def _serialize_project_list(project: Project) -> dict:
    db = get_db_session()
    try:
        chapter_count = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project.id
        ).count()
        total_chunks = db.query(ProjectChunk).join(ProjectSection).join(ProjectChapter).filter(
            ProjectChapter.project_id == project.id
        ).count()
    finally:
        db.close()

    return {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "sourceType": project.source_type,
        "chapterCount": chapter_count,
        "totalChunks": total_chunks,
        "createdAt": project.created_at.isoformat() if project.created_at else None,
        "updatedAt": project.updated_at.isoformat() if project.updated_at else None,
    }


def _serialize_project_full(project: Project, db) -> dict:
    chapters = db.query(ProjectChapter).filter(
        ProjectChapter.project_id == project.id
    ).order_by(ProjectChapter.chapter_index).all()

    chapters_data = []
    for ch in chapters:
        sections = db.query(ProjectSection).filter(
            ProjectSection.chapter_id == ch.id
        ).order_by(ProjectSection.section_index).all()

        sections_data = []
        chapter_word_count = 0
        for sec in sections:
            chunks = db.query(ProjectChunk).filter(
                ProjectChunk.section_id == sec.id
            ).order_by(ProjectChunk.chunk_index).all()

            chunks_data = []
            for chunk in chunks:
                chapter_word_count += chunk.word_count
                chunks_data.append({
                    "id": chunk.id,
                    "sectionId": chunk.section_id,
                    "chunkIndex": chunk.chunk_index,
                    "text": chunk.text,
                    "segmentType": chunk.segment_type,
                    "speaker": chunk.speaker,
                    "emotion": chunk.emotion,
                    "speakerOverride": chunk.speaker_override,
                    "emotionOverride": chunk.emotion_override,
                    "wordCount": chunk.word_count,
                    "approxDurationSeconds": chunk.approx_duration_seconds,
                })

            sections_data.append({
                "id": sec.id,
                "chapterId": sec.chapter_id,
                "sectionIndex": sec.section_index,
                "title": sec.title,
                "status": sec.status,
                "errorMessage": sec.error_message,
                "chunks": chunks_data,
            })

        chapters_data.append({
            "id": ch.id,
            "projectId": ch.project_id,
            "chapterIndex": ch.chapter_index,
            "title": ch.title,
            "status": ch.status,
            "speakersJson": ch.speakers_json,
            "ttsEngine": ch.tts_engine,
            "narratorVoiceId": ch.narrator_voice_id,
            "errorMessage": ch.error_message,
            "wordCount": chapter_word_count,
            "sections": sections_data,
        })

    audio_files = db.query(ProjectAudioFile).filter(
        ProjectAudioFile.project_id == project.id
    ).order_by(ProjectAudioFile.created_at.desc()).all()

    audio_data = [{
        "id": af.id,
        "projectId": af.project_id,
        "scopeType": af.scope_type,
        "scopeId": af.scope_id,
        "format": af.format,
        "durationSeconds": af.duration_seconds,
        "ttsEngine": af.tts_engine,
        "voiceId": af.voice_id,
        "settingsJson": af.settings_json,
        "label": af.label,
        "createdAt": af.created_at.isoformat() if af.created_at else None,
    } for af in audio_files]

    return {
        "id": project.id,
        "title": project.title,
        "status": project.status,
        "ttsEngine": project.tts_engine,
        "narratorVoiceId": project.narrator_voice_id,
        "baseVoiceId": project.base_voice_id,
        "exaggeration": project.exaggeration,
        "pauseDuration": project.pause_duration,
        "speakersJson": project.speakers_json,
        "sourceType": project.source_type,
        "sourceFilename": project.source_filename,
        "errorMessage": project.error_message,
        "outputFormat": project.output_format or "mp3",
        "metaAuthor": project.meta_author,
        "metaNarrator": project.meta_narrator,
        "metaGenre": project.meta_genre,
        "metaYear": project.meta_year,
        "metaDescription": project.meta_description,
        "hasCoverImage": project.meta_cover_image is not None and len(project.meta_cover_image) > 0,
        "createdAt": project.created_at.isoformat() if project.created_at else None,
        "updatedAt": project.updated_at.isoformat() if project.updated_at else None,
        "chapters": chapters_data,
        "audioFiles": audio_data,
    }


@app.get("/projects")
async def list_projects():
    db = get_db_session()
    try:
        projects = db.query(Project).order_by(Project.updated_at.desc()).all()
        return [_serialize_project_list(p) for p in projects]
    finally:
        db.close()


@app.post("/projects")
async def create_project(
    title: str = Form(...),
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    db = get_db_session()
    try:
        project = Project(
            id=str(uuid.uuid4()),
            title=title,
            status="draft",
        )

        if file and file.filename:
            file_content = await file.read()
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

            if ext == "epub":
                from epub_parser import parse_epub
                chapters_data = parse_epub(file_content)
                project.source_type = "epub"
                project.source_filename = file.filename
            elif ext == "txt":
                from epub_parser import parse_txt
                chapters_data = parse_txt(file_content)
                project.source_type = "text"
                project.source_filename = file.filename
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type. Use .txt or .epub")

            db.add(project)
            db.flush()

            for idx, (ch_title, ch_text) in enumerate(chapters_data):
                chapter = ProjectChapter(
                    id=str(uuid.uuid4()),
                    project_id=project.id,
                    chapter_index=idx,
                    title=ch_title,
                    raw_text=ch_text,
                    status="pending",
                )
                db.add(chapter)

        elif text:
            project.source_type = "text"
            db.add(project)
            db.flush()

            chapter = ProjectChapter(
                id=str(uuid.uuid4()),
                project_id=project.id,
                chapter_index=0,
                title=title,
                raw_text=text,
                status="pending",
            )
            db.add(chapter)
        else:
            raise HTTPException(status_code=400, detail="Either text or file is required")

        db.commit()
        db.refresh(project)

        result = _serialize_project_full(project, db)
        return result

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/projects/{project_id}")
async def get_project(project_id: str):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return _serialize_project_full(project, db)
    finally:
        db.close()


@app.patch("/projects/{project_id}")
async def update_project(project_id: str, request: UpdateProjectSettingsRequest):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if request.ttsEngine is not None:
            project.tts_engine = request.ttsEngine
        if request.narratorVoiceId is not None:
            project.narrator_voice_id = request.narratorVoiceId
        if request.baseVoiceId is not None:
            project.base_voice_id = request.baseVoiceId
        if request.exaggeration is not None:
            project.exaggeration = request.exaggeration
        if request.pauseDuration is not None:
            project.pause_duration = request.pauseDuration
        if request.speakersJson is not None:
            project.speakers_json = request.speakersJson
        if request.outputFormat is not None:
            project.output_format = request.outputFormat
        if request.metaAuthor is not None:
            project.meta_author = request.metaAuthor
        if request.metaNarrator is not None:
            project.meta_narrator = request.metaNarrator
        if request.metaGenre is not None:
            project.meta_genre = request.metaGenre
        if request.metaYear is not None:
            project.meta_year = request.metaYear
        if request.metaDescription is not None:
            project.meta_description = request.metaDescription

        project.updated_at = datetime.utcnow()
        db.commit()

        return {"success": True}
    finally:
        db.close()


@app.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        db.delete(project)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.patch("/projects/{project_id}/chapters/{chapter_id}")
async def update_chapter(project_id: str, chapter_id: str, request: UpdateChapterRequest):
    db = get_db_session()
    try:
        chapter = db.query(ProjectChapter).filter(
            ProjectChapter.id == chapter_id,
            ProjectChapter.project_id == project_id
        ).first()
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        if request.ttsEngine is not None:
            chapter.tts_engine = request.ttsEngine
        if request.narratorVoiceId is not None:
            chapter.narrator_voice_id = request.narratorVoiceId
        if request.speakersJson is not None:
            chapter.speakers_json = request.speakersJson

        chapter.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.patch("/projects/{project_id}/chunks/{chunk_id}")
async def update_chunk(project_id: str, chunk_id: str, request: UpdateChunkRequest):
    db = get_db_session()
    try:
        chunk = db.query(ProjectChunk).join(ProjectSection).join(ProjectChapter).filter(
            ProjectChunk.id == chunk_id,
            ProjectChapter.project_id == project_id
        ).first()
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")

        if request.speakerOverride is not None:
            chunk.speaker_override = request.speakerOverride if request.speakerOverride != "" else None
        if request.emotionOverride is not None:
            chunk.emotion_override = request.emotionOverride if request.emotionOverride != "" else None

        chunk.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True}
    finally:
        db.close()


WORDS_PER_SECOND = 2.5

@app.post("/projects/{project_id}/chunks/{chunk_id}/combine-with-previous")
async def combine_chunk_with_previous(project_id: str, chunk_id: str):
    db = get_db_session()
    try:
        chunk = db.query(ProjectChunk).join(ProjectSection).join(ProjectChapter).filter(
            ProjectChunk.id == chunk_id,
            ProjectChapter.project_id == project_id
        ).first()
        if not chunk:
            raise HTTPException(status_code=404, detail="Chunk not found")

        section_chunks = db.query(ProjectChunk).filter(
            ProjectChunk.section_id == chunk.section_id
        ).order_by(ProjectChunk.chunk_index).all()

        prev_chunk = None
        for c in section_chunks:
            if c.id == chunk_id:
                break
            prev_chunk = c

        if not prev_chunk:
            raise HTTPException(status_code=400, detail="No previous chunk to combine with (this is the first chunk)")

        prev_chunk.text = prev_chunk.text.rstrip() + " " + chunk.text.lstrip()
        prev_chunk.word_count = len(prev_chunk.text.split())
        prev_chunk.approx_duration_seconds = round(prev_chunk.word_count / WORDS_PER_SECOND, 1)
        prev_chunk.updated_at = datetime.utcnow()

        db.delete(chunk)
        db.flush()

        remaining = db.query(ProjectChunk).filter(
            ProjectChunk.section_id == prev_chunk.section_id
        ).order_by(ProjectChunk.chunk_index).all()
        for idx, c in enumerate(remaining):
            c.chunk_index = idx

        db.commit()

        project = db.query(Project).filter(Project.id == project_id).first()
        return _serialize_project_full(project, db)
    finally:
        db.close()


class BatchChunkUpdate(BaseModel):
    chunkId: str
    speakerOverride: Optional[str] = None

class BatchChunkUpdateRequest(BaseModel):
    updates: list[BatchChunkUpdate]

@app.post("/projects/{project_id}/chunks/batch-update")
async def batch_update_chunks(project_id: str, request: BatchChunkUpdateRequest):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        chunk_ids = [u.chunkId for u in request.updates]
        chunks = db.query(ProjectChunk).join(ProjectSection).join(ProjectChapter).filter(
            ProjectChunk.id.in_(chunk_ids),
            ProjectChapter.project_id == project_id
        ).all()

        chunk_map = {c.id: c for c in chunks}
        updated = 0

        for update in request.updates:
            chunk = chunk_map.get(update.chunkId)
            if not chunk:
                continue
            if update.speakerOverride is not None:
                chunk.speaker_override = update.speakerOverride if update.speakerOverride != "" else None
            updated += 1

        project.updated_at = datetime.utcnow()
        db.commit()

        all_chunks = db.query(ProjectChunk).join(ProjectSection).join(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).all()
        speakers_set = set()
        for c in all_chunks:
            effective = c.speaker_override or c.speaker
            if effective:
                speakers_set.add(effective)

        existing_speakers = json.loads(project.speakers_json) if project.speakers_json else {}
        new_speakers = {}
        for sp in speakers_set:
            if sp in existing_speakers:
                new_speakers[sp] = existing_speakers[sp]
            else:
                new_speakers[sp] = {"name": sp, "voiceSampleId": None, "pitchOffset": 0, "speedFactor": 1.0}
        project.speakers_json = json.dumps(new_speakers)
        db.commit()

        return {"success": True, "updatedChunks": updated, "speakers": list(speakers_set)}
    finally:
        db.close()


class MergeSpeakersRequest(BaseModel):
    fromSpeaker: str
    toSpeaker: str


@app.post("/projects/{project_id}/speakers/merge")
async def merge_speakers(project_id: str, request: MergeSpeakersRequest):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        chunks = db.query(ProjectChunk).join(ProjectSection).join(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).all()

        updated = 0
        for chunk in chunks:
            effective = chunk.speaker_override or chunk.speaker
            if effective == request.fromSpeaker:
                if chunk.speaker_override:
                    chunk.speaker_override = request.toSpeaker
                else:
                    chunk.speaker = request.toSpeaker
                updated += 1

        speakers = json.loads(project.speakers_json) if project.speakers_json else {}
        if request.fromSpeaker in speakers:
            if request.toSpeaker not in speakers:
                speakers[request.toSpeaker] = speakers[request.fromSpeaker]
            del speakers[request.fromSpeaker]
            project.speakers_json = json.dumps(speakers)

        project.updated_at = datetime.utcnow()
        db.commit()

        remaining_speakers = set()
        for chunk in chunks:
            effective = chunk.speaker_override or chunk.speaker
            if effective:
                remaining_speakers.add(effective)

        return {
            "success": True,
            "updatedChunks": updated,
            "speakers": sorted(remaining_speakers),
        }
    finally:
        db.close()


class SegmentProjectRequest(BaseModel):
    model: str = "openai/gpt-4.1-mini"

@app.post("/projects/{project_id}/segment")
async def segment_project(project_id: str, request: Optional[SegmentProjectRequest] = None):
    model = request.model if request else "openai/gpt-4.1-mini"
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if project.status not in ("draft", "failed", "segmented"):
            raise HTTPException(status_code=400, detail=f"Cannot segment project in state: {project.status}")

        db.query(ProjectChunk).filter(
            ProjectChunk.section_id.in_(
                db.query(ProjectSection.id).join(ProjectChapter).filter(
                    ProjectChapter.project_id == project_id
                )
            )
        ).delete(synchronize_session=False)
        db.query(ProjectSection).filter(
            ProjectSection.chapter_id.in_(
                db.query(ProjectChapter.id).filter(
                    ProjectChapter.project_id == project_id
                )
            )
        ).delete(synchronize_session=False)

        for ch in db.query(ProjectChapter).filter(ProjectChapter.project_id == project_id).all():
            ch.status = "pending"
            ch.error_message = None

        project.status = "segmenting"
        project.error_message = None
        db.commit()
    finally:
        db.close()

    segment_project_background(project_id, model=model)
    return {"success": True, "message": "Segmentation started"}


def _build_segment_data(chunk, chapter, tts_engine, narrator_voice_id, speakers):
    """Build a segment dict from a chunk for job creation."""
    ch_engine = chapter.tts_engine or tts_engine
    ch_narrator = chapter.narrator_voice_id or narrator_voice_id
    speaker = chunk.speaker_override or chunk.speaker
    emotion = chunk.emotion_override or chunk.emotion
    voice_id = ch_narrator
    if speaker and speaker in speakers:
        sp_config = speakers[speaker]
        if isinstance(sp_config, dict) and sp_config.get("voiceSampleId"):
            voice_id = sp_config["voiceSampleId"]
    return {
        "id": chunk.id,
        "text": chunk.text,
        "type": chunk.segment_type,
        "speaker": speaker,
        "sentiment": {"label": emotion} if emotion else None,
        "voice_id": voice_id,
        "tts_engine": ch_engine,
    }


@app.post("/projects/{project_id}/generate")
async def generate_project_audio(project_id: str, request: GenerateProjectAudioRequest):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        tts_engine = project.tts_engine
        narrator_voice_id = project.narrator_voice_id
        base_voice_id = project.base_voice_id
        speakers = json.loads(project.speakers_json) if project.speakers_json else {}
        exaggeration = project.exaggeration
        pause_duration = project.pause_duration

        from job_manager import create_job
        from job_runner import start_job_async

        if request.scopeType == "chunk":
            chunk = db.query(ProjectChunk).join(ProjectSection).join(ProjectChapter).filter(
                ProjectChunk.id == request.scopeId,
                ProjectChapter.project_id == project_id
            ).first()
            if not chunk:
                raise HTTPException(status_code=404, detail="Chunk not found")
            section = db.query(ProjectSection).filter(ProjectSection.id == chunk.section_id).first()
            chapter = db.query(ProjectChapter).filter(ProjectChapter.id == section.chapter_id).first()
            seg = _build_segment_data(chunk, chapter, tts_engine, narrator_voice_id, speakers)
            job_id = create_job(
                title=f"{project.title} — Chunk",
                segments=[seg],
                config={
                    "defaultExaggeration": exaggeration,
                    "pauseBetweenSegments": pause_duration,
                    "speakers": speakers,
                    "ttsEngine": tts_engine,
                    "narratorVoiceId": narrator_voice_id,
                    "baseVoiceId": base_voice_id,
                    "projectId": project_id,
                    "scopeType": "chunk",
                    "scopeId": request.scopeId,
                    "chunkIds": [chunk.id],
                }
            )
            start_job_async(job_id)
            return {"success": True, "jobId": job_id, "totalSegments": 1}

        elif request.scopeType == "section":
            section = db.query(ProjectSection).join(ProjectChapter).filter(
                ProjectSection.id == request.scopeId,
                ProjectChapter.project_id == project_id
            ).first()
            if not section:
                raise HTTPException(status_code=404, detail="Section not found")
            chapter = db.query(ProjectChapter).filter(ProjectChapter.id == section.chapter_id).first()
            chunks = db.query(ProjectChunk).filter(
                ProjectChunk.section_id == section.id
            ).order_by(ProjectChunk.chunk_index).all()
            if not chunks:
                raise HTTPException(status_code=400, detail="No chunks in section")
            segments = [_build_segment_data(c, chapter, tts_engine, narrator_voice_id, speakers) for c in chunks]
            section_label = section.title or f"Section {section.section_index + 1}"
            chapter_title = chapter.title or f"Chapter {chapter.chapter_index + 1}"
            job_id = create_job(
                title=f"{project.title} — {chapter_title} — {section_label}",
                segments=segments,
                config={
                    "defaultExaggeration": exaggeration,
                    "pauseBetweenSegments": pause_duration,
                    "speakers": speakers,
                    "ttsEngine": tts_engine,
                    "narratorVoiceId": narrator_voice_id,
                    "baseVoiceId": base_voice_id,
                    "projectId": project_id,
                    "scopeType": "section",
                    "scopeId": section.id,
                    "sectionId": section.id,
                    "chapterId": chapter.id,
                    "sectionLabel": section_label,
                    "chapterTitle": chapter_title,
                    "chunkIds": [c.id for c in chunks],
                }
            )
            start_job_async(job_id)
            return {"success": True, "jobId": job_id, "totalSegments": len(segments)}

        elif request.scopeType in ("chapter", "project"):
            sections_to_process = []

            if request.scopeType == "chapter":
                chapter = db.query(ProjectChapter).filter(
                    ProjectChapter.id == request.scopeId,
                    ProjectChapter.project_id == project_id
                ).first()
                if not chapter:
                    raise HTTPException(status_code=404, detail="Chapter not found")
                sections = db.query(ProjectSection).filter(
                    ProjectSection.chapter_id == chapter.id
                ).order_by(ProjectSection.section_index).all()
                for sec in sections:
                    chunks = db.query(ProjectChunk).filter(
                        ProjectChunk.section_id == sec.id
                    ).order_by(ProjectChunk.chunk_index).all()
                    if chunks:
                        sections_to_process.append((sec, chapter, chunks))

            else:
                chapters = db.query(ProjectChapter).filter(
                    ProjectChapter.project_id == project_id
                ).order_by(ProjectChapter.chapter_index).all()
                for chapter in chapters:
                    sections = db.query(ProjectSection).filter(
                        ProjectSection.chapter_id == chapter.id
                    ).order_by(ProjectSection.section_index).all()
                    for sec in sections:
                        chunks = db.query(ProjectChunk).filter(
                            ProjectChunk.section_id == sec.id
                        ).order_by(ProjectChunk.chunk_index).all()
                        if chunks:
                            sections_to_process.append((sec, chapter, chunks))

            if not sections_to_process:
                raise HTTPException(status_code=400, detail="No chunks found for the given scope")

            job_group_id = str(uuid.uuid4())
            job_ids = []
            total_segments = 0

            chapter_ids_in_group = list(set(ch.id for _, ch, _ in sections_to_process))

            for sec, chap, chunks in sections_to_process:
                segments = [_build_segment_data(c, chap, tts_engine, narrator_voice_id, speakers) for c in chunks]
                section_label = sec.title or f"Section {sec.section_index + 1}"
                chapter_title = chap.title or f"Chapter {chap.chapter_index + 1}"
                job_id = create_job(
                    title=f"{project.title} — {chapter_title} — {section_label}",
                    segments=segments,
                    config={
                        "defaultExaggeration": exaggeration,
                        "pauseBetweenSegments": pause_duration,
                        "speakers": speakers,
                        "ttsEngine": tts_engine,
                        "narratorVoiceId": narrator_voice_id,
                        "baseVoiceId": base_voice_id,
                        "projectId": project_id,
                        "scopeType": "section",
                        "scopeId": sec.id,
                        "sectionId": sec.id,
                        "chapterId": chap.id,
                        "sectionLabel": section_label,
                        "chapterTitle": chapter_title,
                        "chunkIds": [c.id for c in chunks],
                        "jobGroupId": job_group_id,
                        "groupScopeType": request.scopeType,
                        "groupScopeId": request.scopeId,
                        "chapterIdsInGroup": chapter_ids_in_group,
                    },
                    job_group_id=job_group_id,
                )
                job_ids.append(job_id)
                total_segments += len(segments)

            for jid in job_ids:
                start_job_async(jid)

            return {
                "success": True,
                "jobGroupId": job_group_id,
                "jobIds": job_ids,
                "totalJobs": len(job_ids),
                "totalSegments": total_segments,
            }

        else:
            raise HTTPException(status_code=400, detail="Invalid scope type")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate project audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/projects/{project_id}/audio")
async def list_project_audio(project_id: str):
    db = get_db_session()
    try:
        audio_files = db.query(ProjectAudioFile).filter(
            ProjectAudioFile.project_id == project_id
        ).order_by(ProjectAudioFile.created_at.desc()).all()

        return [{
            "id": af.id,
            "projectId": af.project_id,
            "scopeType": af.scope_type,
            "scopeId": af.scope_id,
            "format": af.format,
            "durationSeconds": af.duration_seconds,
            "ttsEngine": af.tts_engine,
            "voiceId": af.voice_id,
            "settingsJson": af.settings_json,
            "label": af.label,
            "createdAt": af.created_at.isoformat() if af.created_at else None,
        } for af in audio_files]
    finally:
        db.close()


@app.get("/projects/{project_id}/audio/{audio_file_id}")
async def get_project_audio(project_id: str, audio_file_id: str):
    db = get_db_session()
    try:
        af = db.query(ProjectAudioFile).filter(
            ProjectAudioFile.id == audio_file_id,
            ProjectAudioFile.project_id == project_id
        ).first()
        if not af:
            raise HTTPException(status_code=404, detail="Audio file not found")

        media_type = "audio/mpeg" if af.format == "mp3" else "audio/wav"
        return Response(content=af.audio_data, media_type=media_type)
    finally:
        db.close()


@app.post("/projects/{project_id}/cover")
async def upload_cover_image(project_id: str, file: UploadFile = File(...)):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        content = await file.read()
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Cover image must be under 5MB")

        project.meta_cover_image = content
        project.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.get("/projects/{project_id}/cover")
async def get_cover_image(project_id: str):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project or not project.meta_cover_image:
            raise HTTPException(status_code=404, detail="No cover image")

        data = project.meta_cover_image
        mime = "image/jpeg"
        if data[:4] == b'\x89PNG':
            mime = "image/png"
        elif data[:4] == b'RIFF':
            mime = "image/webp"
        return Response(content=data, media_type=mime)
    finally:
        db.close()


@app.delete("/projects/{project_id}/cover")
async def delete_cover_image(project_id: str):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        project.meta_cover_image = None
        project.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.get("/projects/{project_id}/export")
async def export_project(project_id: str, format: str = "mp3"):
    from backend.audio_export import export_single_mp3, export_mp3_per_chapter, export_m4b

    if format not in ("mp3", "mp3-chapters", "m4b"):
        raise HTTPException(status_code=400, detail="Invalid format. Use: mp3, mp3-chapters, m4b")

    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        chapters = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).order_by(ProjectChapter.chapter_index).all()

        chapter_audio = []
        for ch in chapters:
            sections = db.query(ProjectSection).filter(
                ProjectSection.chapter_id == ch.id
            ).order_by(ProjectSection.section_index).all()

            chunk_ids = []
            for sec in sections:
                chunks = db.query(ProjectChunk).filter(
                    ProjectChunk.section_id == sec.id
                ).order_by(ProjectChunk.chunk_index).all()
                chunk_ids.extend([c.id for c in chunks])

            blobs = []
            for cid in chunk_ids:
                af = db.query(ProjectAudioFile).filter(
                    ProjectAudioFile.project_id == project_id,
                    ProjectAudioFile.scope_type == "chunk",
                    ProjectAudioFile.scope_id == cid,
                ).order_by(ProjectAudioFile.created_at.desc()).first()
                if af and af.audio_data:
                    blobs.append(af.audio_data)

            chapter_audio.append((ch.title or f"Chapter {ch.chapter_index + 1}", blobs))

        total_blobs = sum(len(blobs) for _, blobs in chapter_audio)
        if total_blobs == 0:
            raise HTTPException(status_code=400, detail="No audio generated yet. Generate audio before exporting.")

        cover = project.meta_cover_image if project.meta_cover_image else None
        pause_ms = int(project.pause_duration) if project.pause_duration else 500

        kwargs = dict(
            chapter_audio=chapter_audio,
            title=project.title,
            pause_ms=pause_ms,
            author=project.meta_author,
            narrator=project.meta_narrator,
            genre=project.meta_genre,
            year=project.meta_year,
            description=project.meta_description,
            cover_image=cover,
        )

        safe_title = "".join(c for c in project.title if c.isalnum() or c in " _-").strip()

        if format == "mp3":
            data = export_single_mp3(**kwargs)
            return Response(
                content=data,
                media_type="audio/mpeg",
                headers={"Content-Disposition": f'attachment; filename="{safe_title}.mp3"'},
            )
        elif format == "mp3-chapters":
            data = export_mp3_per_chapter(**kwargs)
            return Response(
                content=data,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{safe_title} - Chapters.zip"'},
            )
        elif format == "m4b":
            data = export_m4b(**kwargs)
            return Response(
                content=data,
                media_type="audio/x-m4b",
                headers={"Content-Disposition": f'attachment; filename="{safe_title}.m4b"'},
            )

    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
