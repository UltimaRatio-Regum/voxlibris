"""
Narrator AI - FastAPI Backend
Text to Audiobook Generator with Chatterbox TTS
"""

from dotenv import load_dotenv
load_dotenv()  # loads .env if present; never overrides vars already set in the environment

import os
import re
import json
import uuid
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request as FastAPIRequest
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
    Project, ProjectChapter, ProjectSection, ProjectChunk, ProjectAudioFile,
    AppSetting, TTSJob, JobStatus,
)
from remote_tts_client import RemoteTTSClient
from project_segmenter import segment_project_background, split_into_sections, _call_llm_for_section, rechunk_section

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TARGET_CHUNK_WORDS = 30
MAX_CHUNK_WORDS = 40

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

import os as _os
_cors_origins = [o.strip() for o in _os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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


def _get_user_info(request: FastAPIRequest) -> tuple[Optional[str], str]:
    """Extract user_id and user_role from proxy-forwarded headers."""
    user_id = request.headers.get("X-User-Id")
    user_role = request.headers.get("X-User-Role", "user")
    return user_id, user_role


def _require_project_access(db, user_id: Optional[str], user_role: str, project_id: str):
    """Verify the user has access to the given project. Raises 404 if not found or unauthorized."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if user_role != "administrator" and project.user_id != user_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_voice_access(db, user_id: Optional[str], user_role: str, voice_id: str):
    """Verify the user has access to the given custom voice."""
    voice = db.query(CustomVoice).filter(CustomVoice.id == voice_id).first()
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found")
    if user_role != "administrator" and voice.user_id != user_id:
        raise HTTPException(status_code=404, detail="Voice not found")
    return voice


def _require_engine_access(db, user_id: Optional[str], user_role: str, engine_id: str, write: bool = False):
    """Verify the user has access to the given engine. For write ops on shared engines, require admin."""
    engine = db.query(TTSEngineEndpoint).filter(TTSEngineEndpoint.engine_id == engine_id).first()
    if not engine:
        raise HTTPException(status_code=404, detail="Engine not found")
    if user_role == "administrator":
        return engine
    if engine.is_shared:
        if write:
            raise HTTPException(status_code=403, detail="Only admins can modify shared engines")
        return engine
    if user_id and engine.user_id and engine.user_id != user_id:
        raise HTTPException(status_code=404, detail="Engine not found")
    return engine


def _require_job_access(db, user_id: Optional[str], user_role: str, job_id: str):
    """Verify the user has access to the given job."""
    from database import TTSJob
    job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if user_role != "administrator" and job.user_id != user_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


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
    request: FastAPIRequest,
    name: str = Form(...),
    file: UploadFile = File(...),
):
    """Upload a voice sample for cloning, persisted to database"""
    user_id, user_role = _get_user_info(request)
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
                user_id=user_id,
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
async def get_custom_voice_audio(voice_id: str, request: FastAPIRequest):
    """Stream custom voice audio from database"""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        voice = _require_voice_access(db, user_id, user_role, voice_id)
        media_type = "audio/wav" if voice.file_ext in [".wav", ""] else f"audio/{voice.file_ext.lstrip('.')}"
        return Response(content=voice.audio_data, media_type=media_type)
    finally:
        db.close()


@app.get("/custom-voices")
async def list_custom_voices(request: FastAPIRequest):
    """List all custom voices from the database"""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        query = db.query(CustomVoice)
        if user_id and user_role != "administrator":
            query = query.filter(CustomVoice.user_id == user_id)
        voices = query.order_by(CustomVoice.created_at.desc()).all()
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
async def rename_custom_voice(voice_id: str, request: FastAPIRequest, name: str = Form(...)):
    """Rename a custom voice"""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        voice = _require_voice_access(db, user_id, user_role, voice_id)
        voice.name = name
        db.commit()
        if voice_id in voice_samples:
            voice_samples[voice_id].name = name
        return {"success": True, "name": name}
    finally:
        db.close()


@app.delete("/voices/{voice_id}")
async def delete_voice(voice_id: str, request: FastAPIRequest):
    """Delete a voice sample from database"""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        voice = _require_voice_access(db, user_id, user_role, voice_id)
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



@app.get("/tts-engines")
async def list_tts_engines(request: FastAPIRequest):
    """List all registered TTS engine endpoints from the database."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        query = db.query(TTSEngineEndpoint).filter(TTSEngineEndpoint.is_active == True)
        if user_id and user_role != "administrator":
            from sqlalchemy import or_
            query = query.filter(or_(
                TTSEngineEndpoint.is_shared == True,
                TTSEngineEndpoint.user_id == user_id,
            ))
        engines = query.all()
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
                "is_shared": e.is_shared,
                "user_id": e.user_id,
            })
        return result
    finally:
        db.close()


class AddEngineRequestV2(BaseModel):
    url: str
    api_key: Optional[str] = None
    is_shared: bool = False


@app.post("/tts-engines")
async def add_tts_engine(req: FastAPIRequest, request_body: AddEngineRequestV2 = None):
    """Register a new TTS engine by URL. Queries GetEngineDetails and stores in DB."""
    user_id, user_role = _get_user_info(req)
    
    if request_body is None:
        body = await req.json()
        url = body.get("url", "")
        api_key = body.get("api_key")
        is_shared_req = body.get("is_shared", False)
    else:
        url = request_body.url
        api_key = request_body.api_key
        is_shared_req = request_body.is_shared
    
    if is_shared_req and user_role != "administrator":
        raise HTTPException(status_code=403, detail="Only administrators can create shared engines")
    
    try:
        client = RemoteTTSClient(url, api_key)
        details = await client.get_engine_details()
    except Exception as e:
        logger.error(f"Failed to query engine at {url}: {e}")
        raise HTTPException(status_code=400, detail=f"Could not reach engine: {str(e)}")

    db = get_db_session()
    try:
        existing = db.query(TTSEngineEndpoint).filter(
            TTSEngineEndpoint.engine_id == details.engine_id
        ).first()
        if existing:
            if user_role != "administrator":
                if existing.is_shared or (existing.user_id and existing.user_id != user_id):
                    raise HTTPException(status_code=403, detail="Cannot modify this engine")
            existing.engine_name = details.engine_name
            existing.base_url = url.rstrip("/")
            existing.api_key = api_key
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
                base_url=url.rstrip("/"),
                api_key=api_key,
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
                is_shared=is_shared_req,
                user_id=user_id,
                last_tested_at=datetime.utcnow(),
                last_test_success=True,
            )
            db.add(entry)
            db.commit()
            return {"status": "added", "engine_id": details.engine_id, "engine_name": details.engine_name}
    finally:
        db.close()


@app.post("/tts-engines/{engine_id}/test")
async def test_tts_engine(engine_id: str, request: FastAPIRequest):
    """Test connectivity to a registered TTS engine."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        entry = _require_engine_access(db, user_id, user_role, engine_id)

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
async def remove_tts_engine(engine_id: str, request: FastAPIRequest):
    """Remove a registered TTS engine."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        entry = _require_engine_access(db, user_id, user_role, engine_id, write=True)
        db.delete(entry)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.get("/voice-library-db")
async def get_voice_library_db(request: FastAPIRequest):
    """Get all voices from the PostgreSQL voice library."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        query = db.query(VoiceLibraryEntry)
        if user_id and user_role != "administrator":
            from sqlalchemy import or_
            query = query.filter(or_(
                VoiceLibraryEntry.is_shared == True,
                VoiceLibraryEntry.user_id == user_id,
            ))
        voices = query.all()
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
async def get_voice_audio(voice_id: str, request: FastAPIRequest):
    """Stream voice sample audio from the database."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        voice = db.query(VoiceLibraryEntry).filter(VoiceLibraryEntry.id == voice_id).first()
        if not voice or not voice.audio_data:
            raise HTTPException(status_code=404, detail="Voice audio not found")
        if user_role != "administrator" and not voice.is_shared and voice.user_id != user_id:
            raise HTTPException(status_code=404, detail="Voice audio not found")
        return Response(content=voice.audio_data, media_type="audio/wav")
    finally:
        db.close()


@app.get("/voice-library-db/{voice_id}/alt-audio")
async def get_voice_alt_audio(voice_id: str, request: FastAPIRequest):
    """Stream alternate voice sample audio from the database."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        voice = db.query(VoiceLibraryEntry).filter(VoiceLibraryEntry.id == voice_id).first()
        if not voice or not voice.alt_audio_data:
            raise HTTPException(status_code=404, detail="Alternate voice audio not found")
        if user_role != "administrator" and not voice.is_shared and voice.user_id != user_id:
            raise HTTPException(status_code=404, detail="Alternate voice audio not found")
        return Response(content=voice.alt_audio_data, media_type="audio/wav")
    finally:
        db.close()


@app.post("/voice-library-db")
async def upload_voice_to_library(
    request: FastAPIRequest,
    name: str = Form(...),
    gender: str = Form(...),
    age: int = Form(0),
    language: str = Form(""),
    location: str = Form(""),
    transcript: str = Form(""),
    file: UploadFile = File(...),
):
    """Upload a voice sample to the PostgreSQL voice library."""
    user_id, user_role = _get_user_info(request)
    if user_role != "administrator":
        raise HTTPException(status_code=403, detail="Only administrators can upload to the voice library")
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
                is_shared=True,
                user_id=user_id,
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
async def delete_voice_from_library(voice_id: str, request: FastAPIRequest):
    """Delete a voice from the PostgreSQL voice library."""
    user_id, user_role = _get_user_info(request)
    if user_role != "administrator":
        raise HTTPException(status_code=403, detail="Only administrators can delete voice library entries")
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

    async def call_llm_for_chunk(client: httpx.AsyncClient, chunk: str, known_speakers: list[str], context: str) -> dict:
        """Call shared LLM parsing function from project_segmenter."""
        try:
            return await _call_llm_for_section(
                client, chunk, known_speakers, context,
                request.model, OPENROUTER_BASE_URL, OPENROUTER_API_KEY
            )
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
    """Parse text using LLM (non-streaming fallback) — delegates to shared parsing function."""
    import httpx

    OPENROUTER_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")

    CANONICAL_EMOTIONS = [
        "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
        "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
    ]

    try:
        async with httpx.AsyncClient() as client:
            result = await _call_llm_for_section(
                client, request.text[:8000],
                request.knownSpeakers or [], "",
                request.model, OPENROUTER_BASE_URL, OPENROUTER_API_KEY
            )

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
    get_segment_audio, cancel_job, delete_job, run_cleanup_loop,
    TTS_OUTPUT_DIR,
)
from job_runner import start_job_async

init_database()


@app.on_event("startup")
async def startup_event():
    """Run cleanup loop on startup, load custom voices, seed settings, reset orphaned jobs."""
    import asyncio
    _load_custom_voices_from_db()
    _seed_parsing_prompt()
    _reset_orphaned_waiting_jobs()
    asyncio.create_task(run_cleanup_loop())


def _reset_orphaned_waiting_jobs():
    """Reset any jobs stuck in WAITING/PROCESSING and re-queue PENDING jobs from a previous process."""
    from job_runner import start_job_async
    from export_runner import _run_export
    import threading
    db = get_db_session()
    try:
        orphaned = db.query(TTSJob).filter(
            TTSJob.status.in_([JobStatus.WAITING.value, JobStatus.PROCESSING.value])
        ).all()
        for job in orphaned:
            job.status = JobStatus.PENDING.value
            job.error_message = None
        if orphaned:
            db.commit()
            logger.info(f"Reset {len(orphaned)} orphaned jobs to pending")

        pending = db.query(TTSJob).filter(
            TTSJob.status == JobStatus.PENDING.value
        ).order_by(TTSJob.created_at.asc()).all()
        tts_pending_ids = []
        export_pending_ids = []
        for job in pending:
            jt = getattr(job, 'job_type', 'tts') or 'tts'
            if jt == "export":
                export_pending_ids.append(job.id)
            else:
                tts_pending_ids.append(job.id)
    finally:
        db.close()

    if tts_pending_ids:
        logger.info(f"Re-queuing {len(tts_pending_ids)} pending TTS jobs through engine mutex")
        for job_id in tts_pending_ids:
            start_job_async(job_id)
    if export_pending_ids:
        logger.info(f"Re-queuing {len(export_pending_ids)} pending export jobs")
        for job_id in export_pending_ids:
            threading.Thread(target=_run_export, args=(job_id,), daemon=True).start()


class CreateJobRequest(BaseModel):
    title: str = "Untitled"
    segments: list
    config: dict


@app.post("/jobs")
async def create_tts_job(request: CreateJobRequest, req: FastAPIRequest):
    """Create a new TTS generation job."""
    user_id, user_role = _get_user_info(req)
    try:
        job_id = create_job(
            title=request.title,
            segments=request.segments,
            config=request.config,
            user_id=user_id,
        )
        
        start_job_async(job_id)
        
        return {"jobId": job_id, "status": "pending"}
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs")
async def list_jobs(request: FastAPIRequest, include_completed: bool = True, limit: int = 20, offset: int = 0):
    """List all TTS jobs with pagination."""
    user_id, user_role = _get_user_info(request)
    try:
        return get_all_jobs(include_completed=include_completed, limit=limit, offset=offset, user_id=user_id, user_role=user_role)
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str, request: FastAPIRequest):
    """Get status of a TTS job."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_job_access(db, user_id, user_role, job_id)
    finally:
        db.close()
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/segments")
async def get_job_segments_endpoint(job_id: str, request: FastAPIRequest, completed_only: bool = False):
    """Get segments for a job."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_job_access(db, user_id, user_role, job_id)
    finally:
        db.close()
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    segments = get_job_segments(job_id, completed_only=completed_only)
    return {"segments": segments}


@app.get("/jobs/{job_id}/segments/{segment_id}/audio")
async def get_segment_audio_endpoint(job_id: str, segment_id: str, request: FastAPIRequest):
    """Get audio for a specific segment."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_job_access(db, user_id, user_role, job_id)
    finally:
        db.close()
    from fastapi.responses import Response
    
    audio_data = get_segment_audio(segment_id)
    if not audio_data:
        raise HTTPException(status_code=404, detail="Audio not found")
    
    return Response(
        content=audio_data,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"inline; filename=segment_{segment_id}.mp3"}
    )


@app.post("/jobs/clear-completed")
async def clear_completed_jobs(request: FastAPIRequest):
    """Delete finished jobs (completed, failed, cancelled) for the calling user."""
    user_id, user_role = _get_user_info(request)
    from sqlalchemy import text
    db = get_db_session()
    try:
        query = db.query(TTSJob).filter(
            TTSJob.status.in_([JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value])
        )
        if user_role != "administrator":
            query = query.filter(TTSJob.user_id == user_id)
        finished = query.all()
        if not finished:
            return {"deleted": 0}

        job_ids = [j.id for j in finished]
        export_audio_ids = [j.output_audio_file_id for j in finished if getattr(j, 'output_audio_file_id', None)]

        for jid in job_ids:
            cancel_job(jid)

        from database import TTSSegment
        db.query(TTSSegment).filter(TTSSegment.job_id.in_(job_ids)).delete(synchronize_session=False)

        for job in finished:
            db.delete(job)

        if export_audio_ids:
            db.query(ProjectAudioFile).filter(ProjectAudioFile.id.in_(export_audio_ids)).delete(synchronize_session=False)

        db.commit()

        for jid in job_ids:
            job_dir = os.path.join(TTS_OUTPUT_DIR, jid)
            if os.path.exists(job_dir):
                import shutil
                shutil.rmtree(job_dir, ignore_errors=True)

        return {"deleted": len(job_ids)}
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing completed jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.post("/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: str, request: FastAPIRequest):
    """Cancel a running job."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_job_access(db, user_id, user_role, job_id)
    finally:
        db.close()
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    cancel_job(job_id)
    return {"status": "cancelled"}


@app.post("/jobs/{job_id}/retry")
async def retry_job_endpoint(job_id: str, request: FastAPIRequest):
    """Retry a failed job by resetting failed segments and re-running."""
    from job_runner import start_job_async
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        job = _require_job_access(db, user_id, user_role, job_id)
        if job.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
            raise HTTPException(status_code=400, detail="Only failed or cancelled jobs can be retried")

        failed_segs = db.query(TTSSegment).filter(
            TTSSegment.job_id == job_id,
            TTSSegment.status.in_([SegmentStatus.FAILED.value, SegmentStatus.PENDING.value])
        ).all()
        for seg in failed_segs:
            seg.status = SegmentStatus.PENDING.value
            seg.error_message = None

        job.status = JobStatus.PENDING.value
        job.error_message = None
        job.failed_segments = 0
        db.commit()
    finally:
        db.close()

    start_job_async(job_id)
    return {"status": "retrying", "jobId": job_id}


@app.delete("/jobs/{job_id}")
async def delete_job_endpoint(job_id: str, request: FastAPIRequest):
    """Delete a job and its segments."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_job_access(db, user_id, user_role, job_id)
    finally:
        db.close()
    if delete_job(job_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/jobs/{job_id}/audio")
async def get_combined_audio(job_id: str, request: FastAPIRequest, max_silence_ms: int = 300):
    """Get combined audio for all completed segments with silence compression."""
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_job_access(db, user_id, user_role, job_id)
    finally:
        db.close()
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
    request: FastAPIRequest,
    file: UploadFile = File(...),
    tts_engine: str = Form("edge-tts"),
):
    """Upload a .txt or .epub file for processing."""
    user_id, _ = _get_user_info(request)
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = file.filename.lower().split('.')[-1]
    if ext not in ('txt', 'epub'):
        raise HTTPException(status_code=400, detail="Only .txt and .epub files are supported")

    MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds maximum allowed size of 50 MB")
        upload = upload_manager.create_upload(
            filename=file.filename,
            file_content=content,
            tts_engine=tts_engine,
            user_id=user_id
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
async def start_analysis(upload_id: str, request: FastAPIRequest):
    """Start background analysis for an upload."""
    user_id, user_role = _get_user_info(request)
    upload = upload_manager.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if user_role != "administrator" and upload.get("userId") != user_id:
        raise HTTPException(status_code=404, detail="Upload not found")

    upload_manager.start_analysis(
        upload_id
    )
    
    return {"status": "analyzing", "uploadId": upload_id}


@app.get("/uploads")
async def list_uploads(request: FastAPIRequest, limit: int = 20):
    """List recent uploads for the calling user."""
    user_id, user_role = _get_user_info(request)
    uploads = upload_manager.list_uploads(limit=limit, user_id=user_id, user_role=user_role)
    return {"uploads": uploads}


def _require_upload_access(upload: dict, user_id: str, user_role: str):
    """Raise 404 if user does not own the upload (admins always have access)."""
    if user_role != "administrator" and upload.get("userId") != user_id:
        raise HTTPException(status_code=404, detail="Upload not found")


@app.get("/uploads/{upload_id}")
async def get_upload(upload_id: str, request: FastAPIRequest):
    """Get upload status and chapters."""
    user_id, user_role = _get_user_info(request)
    upload = upload_manager.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    _require_upload_access(upload, user_id, user_role)
    return upload


@app.get("/uploads/{upload_id}/chapters/{chapter_id}/analysis")
async def get_chapter_analysis(upload_id: str, chapter_id: str, request: FastAPIRequest):
    """Get analysis results for a specific chapter."""
    user_id, user_role = _get_user_info(request)
    upload = upload_manager.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    _require_upload_access(upload, user_id, user_role)
    analysis = upload_manager.get_chapter_analysis(chapter_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@app.delete("/uploads/{upload_id}")
async def delete_upload(upload_id: str, request: FastAPIRequest):
    """Delete an upload and all its chapters."""
    user_id, user_role = _get_user_info(request)
    upload = upload_manager.get_upload(upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    _require_upload_access(upload, user_id, user_role)
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
async def generate_from_upload(upload_id: str, request: GenerateFromUploadRequest, req: FastAPIRequest):
    """Generate TTS jobs from an analyzed upload."""
    gen_user_id, gen_user_role = _get_user_info(req)
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
            config=config,
            user_id=gen_user_id,
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
async def update_prosody_settings(request: ProsodySettingsRequest, req: FastAPIRequest):
    """Update the emotion prosody settings with validation. Requires administrator role."""
    _, user_role = _get_user_info(req)
    if user_role != "administrator":
        raise HTTPException(status_code=403, detail="Administrator access required")
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


PARSING_PROMPT_SETTING_KEY = "parsing_prompt"

INITIAL_PARSING_PROMPT = """You are splitting text into individual sentences for a text-to-speech audiobook engine. Your ONLY job is to split at sentence boundaries and quote boundaries, and assign speaker/emotion metadata. Do NOT consider chunk length or word count at all.

SPLITTING RULES — THESE ARE THE ONLY VALID SPLIT POINTS:
1. SENTENCE BOUNDARIES: Split at every sentence ending (period, question mark, exclamation mark). Each sentence becomes its own segment.
2. QUOTE BOUNDARIES: Always split where dialogue (quoted text) begins or ends. Quoted dialogue must always be its own segment, separate from surrounding narration. Never mix dialogue and narration in one segment. If a quoted segment starts mid-sentence, that is a valid split point.
3. NO OTHER SPLITS: Do NOT split for any other reason. Do not split at commas, conjunctions, prepositions, or any other point within a sentence. Keep each complete sentence as a single segment regardless of how long it is. A 50-word sentence stays as one segment. A 60-word sentence stays as one segment.

TYPE: Each segment is either "spoken" (dialogue in quotes) or "narration" (everything else).

SPEAKER IDENTIFICATION — CRITICAL:
You MUST identify a speaker for EVERY spoken segment. Never leave speaker_candidates empty or omit it. Use ALL available evidence to determine who is speaking:

1. EXPLICIT DIALOGUE TAGS: "said John", "Mary whispered", "he replied" — use the named character directly.
2. PRONOUN RESOLUTION: If the tag says "he said" or "she asked", look at the surrounding narration to determine which character "he" or "she" refers to. Assign that character as the speaker.
3. TURN-TAKING ORDER: In a conversation between two or more characters, speakers typically alternate. If Character A spoke last, the next quote is very likely Character B. Use this pattern.
4. NARRATIVE CONTEXT: If narration describes a character's actions or thoughts immediately before a quote (e.g., "John stepped forward. \\"Let's go.\\""), that character is almost certainly the speaker.
5. CONTENT AND TONE: What is said can indicate who is speaking — a character's known personality, role, or speech patterns can help identify them.
6. SCENE CONTEXT: Consider who is present in the scene. If only two characters are in a room, all dialogue must be between them.
7. BEST GUESS AT LOW CONFIDENCE: If you cannot determine the speaker with high confidence, you MUST still provide your best guess. A low-confidence identification (e.g., 0.4) is far better than no identification at all. Use "Unknown" only as an absolute last resort when there are zero contextual clues whatsoever.

Examples of speaker inference:
- "She turned to leave. \\"I'll be back,\\" she promised." → The speaker is whoever "she" refers to in context. Assign that character with high confidence.
- After a line from John: "\\"That's ridiculous!\\"" (no dialogue tag) → Likely the other character in the conversation (turn-taking). Assign with moderate confidence (0.6-0.7).
- "The doctor examined the chart. \\"We need to operate immediately.\\"" → The doctor is speaking (narrative context). Assign with high confidence.

EMOTION: Assign exactly one emotion per segment from this FIXED list ONLY: ${VALID_EMOTIONS}

| Emotion    | Use When                                           |
|------------|---------------------------------------------------|
| neutral    | Default, factual narration, no strong emotion     |
| happy      | Joy, pleasure, satisfaction, positive outcomes    |
| sad        | Sorrow, disappointment, loss, grief               |
| angry      | Frustration, rage, annoyance, confrontation       |
| fear       | Fear, worry, dread, danger, threat                |
| disgust    | Revulsion, disapproval, distaste                  |
| surprise   | Shock, astonishment, unexpected events            |
| excited    | Enthusiasm, anticipation, energy, thrill          |
| calm       | Peaceful, serene, relaxed, reassuring             |
| anxious    | Nervousness, unease, tension, apprehension        |
| hopeful    | Optimism, anticipation of good, looking forward   |
| melancholy | Wistful sadness, nostalgia, bittersweet feelings  |
| tender     | Gentle affection, warmth, intimacy, caring        |
| proud      | Achievement, dignity, self-assurance, satisfaction|

EXAMPLE — given: "She walked through the crowded marketplace, scanning the stalls for anything useful. The smell of fresh bread drifted from a nearby bakery, mixing with the sharp tang of fish from the harbor. \\"Looking for something specific?\\" the old merchant asked, leaning forward."

Correct output — 3 segments in 1 chunk, NOT 1 large segment:
- Segment 1 (narration, 13w): "She walked through the crowded marketplace, scanning the stalls for anything useful."
- Segment 2 (narration, 20w): "The smell of fresh bread drifted from a nearby bakery, mixing with the sharp tang of fish from the harbor."
- Segment 3 (spoken, 8w): "\\"Looking for something specific?\\" the old merchant asked, leaning forward." → speaker_candidates: {{"the old merchant": 0.95}}

Return JSON in this exact format:
{{
  "characters": ["Character Name 1", "Character Name 2"],
  "chunks": [
    {{
      "chunk_id": 1,
      "approx_duration_seconds": 10,
      "segments": [
        {{
          "type": "spoken",
          "text": "The exact quoted text including quotes",
          "speaker_candidates": {{"CharacterA": 0.9, "CharacterB": 0.1}},
          "emotion": {{"label": "happy", "score": 0.8}}
        }},
        {{
          "type": "narration",
          "text": "The narration text",
          "emotion": {{"label": "neutral", "score": 0.7}}
        }}
      ]
    }}
  ]
}}

Important:
- Preserve the EXACT text including quotation marks — do not paraphrase, summarize, or omit words
- Include ALL text with no gaps
- Chunk IDs should be sequential starting from the provided starting ID
- Use context from previous exchanges to identify speakers consistently
- ONLY use emotions from the fixed list above — do not invent new emotion labels
- EVERY spoken segment MUST have a non-empty speaker_candidates object — never omit it"""


def _seed_parsing_prompt():
    db = get_db_session()
    try:
        existing = db.query(AppSetting).filter(AppSetting.key == PARSING_PROMPT_SETTING_KEY).first()
        if not existing:
            setting = AppSetting(key=PARSING_PROMPT_SETTING_KEY, value=INITIAL_PARSING_PROMPT)
            db.add(setting)
            db.commit()
            logger.info("Seeded initial parsing prompt into database")
    except Exception as e:
        db.rollback()
        logger.warning(f"Failed to seed parsing prompt: {e}")
    finally:
        db.close()


@app.get("/parsing-prompt")
async def get_parsing_prompt():
    """Get the current parsing prompt from the database."""
    db = get_db_session()
    try:
        setting = db.query(AppSetting).filter(AppSetting.key == PARSING_PROMPT_SETTING_KEY).first()
        if setting and setting.value:
            return {"prompt": setting.value}
        return {"prompt": ""}
    finally:
        db.close()


class ParsingPromptRequest(BaseModel):
    prompt: str


@app.post("/parsing-prompt")
async def update_parsing_prompt(request: ParsingPromptRequest):
    """Save the parsing prompt to the database."""
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")
    db = get_db_session()
    try:
        setting = db.query(AppSetting).filter(AppSetting.key == PARSING_PROMPT_SETTING_KEY).first()
        if setting:
            setting.value = request.prompt
        else:
            setting = AppSetting(key=PARSING_PROMPT_SETTING_KEY, value=request.prompt)
            db.add(setting)
        db.commit()
        logger.info("Saved parsing prompt to database")
        return {"success": True}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save parsing prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


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
async def update_tts_settings(request: TTSSettingsRequest, req: FastAPIRequest):
    """Update the TTS model settings. Requires administrator role."""
    _, user_role = _get_user_info(req)
    if user_role != "administrator":
        raise HTTPException(status_code=403, detail="Administrator access required")
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
    narratorSpeed: Optional[float] = None
    baseVoiceId: Optional[str] = None
    exaggeration: Optional[float] = None
    pauseDuration: Optional[float] = None
    speakersJson: Optional[str] = None
    narratorEmotion: Optional[str] = None
    dialogueEmotionMode: Optional[str] = None
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
    segmentType: Optional[str] = None


class BulkUpdateChunksRequest(BaseModel):
    chunkIds: list[str]
    speakerOverride: Optional[str] = None
    emotionOverride: Optional[str] = None
    segmentType: Optional[str] = None


class GenerateProjectAudioRequest(BaseModel):
    scopeType: str
    scopeId: str
    onlyMissing: Optional[bool] = False


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
                "hasRawText": sec.raw_text is not None and len(sec.raw_text) > 0,
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
        "narratorSpeed": project.narrator_speed if hasattr(project, 'narrator_speed') and project.narrator_speed is not None else 1.0,
        "baseVoiceId": project.base_voice_id,
        "exaggeration": project.exaggeration,
        "pauseDuration": project.pause_duration,
        "speakersJson": project.speakers_json,
        "narratorEmotion": project.narrator_emotion or "auto",
        "dialogueEmotionMode": project.dialogue_emotion_mode or "per-chunk",
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
async def list_projects(request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        query = db.query(Project)
        if user_id and user_role != "administrator":
            query = query.filter(
                Project.user_id == user_id
            )
        projects = query.order_by(Project.updated_at.desc()).all()
        return [_serialize_project_list(p) for p in projects]
    finally:
        db.close()


def _title_exists(db, user_id: Optional[str], candidate: str) -> bool:
    """Check if a project with this title already exists for the user."""
    query = db.query(Project).filter(Project.title == candidate)
    if user_id:
        query = query.filter(Project.user_id == user_id)
    return query.first() is not None


def _generate_unique_title(db, user_id: Optional[str], base_title: str) -> str:
    """Return base_title if unique, otherwise append ' #2', ' #3', etc."""
    if not _title_exists(db, user_id, base_title):
        return base_title
    n = 2
    while True:
        candidate = f"{base_title} #{n}"
        if not _title_exists(db, user_id, candidate):
            return candidate
        n += 1


def _generate_untitled_name(db, user_id: Optional[str]) -> str:
    """Return 'Untitled Book #X' where X is the smallest unused integer >= 1."""
    n = 1
    while True:
        candidate = f"Untitled Book #{n}"
        if not _title_exists(db, user_id, candidate):
            return candidate
        n += 1


@app.post("/projects")
async def create_project(
    request: FastAPIRequest,
    title: str = Form(""),
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        epub_metadata = None
        chapters_data = None
        source_type = "text"
        source_filename = None

        if file and file.filename:
            file_content = await file.read()
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

            if ext == "epub":
                from epub_parser import parse_epub_with_metadata
                result = parse_epub_with_metadata(file_content)
                chapters_data = result["chapters"]
                epub_metadata = result["metadata"]
                source_type = "epub"
                source_filename = file.filename
            elif ext == "txt":
                from epub_parser import parse_txt
                chapters_data = parse_txt(file_content)
                source_type = "text"
                source_filename = file.filename
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type. Use .txt or .epub")
        elif not text:
            raise HTTPException(status_code=400, detail="Either text or file is required")

        user_title = title.strip()

        if user_title:
            if _title_exists(db, user_id, user_title):
                raise HTTPException(status_code=409, detail="A project with this title already exists")
            final_title = user_title
        elif source_type == "epub" and epub_metadata and epub_metadata.get("title"):
            final_title = _generate_unique_title(db, user_id, epub_metadata["title"])
        elif source_type == "text" and not file:
            final_title = _generate_untitled_name(db, user_id)
        else:
            final_title = _generate_untitled_name(db, user_id)

        project = Project(
            id=str(uuid.uuid4()),
            title=final_title,
            status="draft",
            user_id=user_id,
            source_type=source_type,
            source_filename=source_filename,
        )

        if epub_metadata:
            if epub_metadata.get("author"):
                project.meta_author = epub_metadata["author"]
            if epub_metadata.get("year"):
                project.meta_year = epub_metadata["year"]
            if epub_metadata.get("description"):
                project.meta_description = epub_metadata["description"]
            if epub_metadata.get("cover_image"):
                project.meta_cover_image = epub_metadata["cover_image"]

        if chapters_data is not None:
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
            db.add(project)
            db.flush()

            chapter = ProjectChapter(
                id=str(uuid.uuid4()),
                project_id=project.id,
                chapter_index=0,
                title=final_title,
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
async def get_project(project_id: str, request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)
        return _serialize_project_full(project, db)
    finally:
        db.close()


@app.patch("/projects/{project_id}")
async def update_project(project_id: str, request: UpdateProjectSettingsRequest, req: FastAPIRequest):
    user_id, user_role = _get_user_info(req)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)

        if request.ttsEngine is not None:
            project.tts_engine = request.ttsEngine
        if request.narratorVoiceId is not None:
            project.narrator_voice_id = request.narratorVoiceId
        if request.narratorSpeed is not None:
            project.narrator_speed = max(0.5, min(2.0, request.narratorSpeed))
        if request.baseVoiceId is not None:
            project.base_voice_id = request.baseVoiceId
        if request.exaggeration is not None:
            project.exaggeration = request.exaggeration
        if request.pauseDuration is not None:
            project.pause_duration = request.pauseDuration
        if request.speakersJson is not None:
            project.speakers_json = request.speakersJson
        if request.narratorEmotion is not None:
            project.narrator_emotion = request.narratorEmotion
        if request.dialogueEmotionMode is not None:
            project.dialogue_emotion_mode = request.dialogueEmotionMode
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
async def delete_project(project_id: str, request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)

        db.delete(project)
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.patch("/projects/{project_id}/chapters/{chapter_id}")
async def update_chapter(project_id: str, chapter_id: str, request: UpdateChapterRequest, req: FastAPIRequest):
    user_id, user_role = _get_user_info(req)
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)
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
async def update_chunk(project_id: str, chunk_id: str, request: UpdateChunkRequest, req: FastAPIRequest):
    user_id, user_role = _get_user_info(req)
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)
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
        if request.segmentType is not None:
            if request.segmentType in ("narration", "dialogue"):
                chunk.segment_type = request.segmentType

        chunk.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.post("/projects/{project_id}/chunks/bulk-update")
async def bulk_update_chunks(project_id: str, request: BulkUpdateChunksRequest, req: FastAPIRequest):
    user_id, user_role = _get_user_info(req)
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)

        if not request.chunkIds:
            raise HTTPException(status_code=400, detail="No chunk IDs provided")

        chunks = db.query(ProjectChunk).join(ProjectSection).join(ProjectChapter).filter(
            ProjectChunk.id.in_(request.chunkIds),
            ProjectChapter.project_id == project_id
        ).all()

        if len(chunks) == 0:
            raise HTTPException(status_code=404, detail="No matching chunks found")

        now = datetime.utcnow()
        for chunk in chunks:
            if request.speakerOverride is not None:
                chunk.speaker_override = request.speakerOverride if request.speakerOverride != "" else None
            if request.emotionOverride is not None:
                chunk.emotion_override = request.emotionOverride if request.emotionOverride != "" else None
            if request.segmentType is not None:
                if request.segmentType in ("narration", "dialogue"):
                    chunk.segment_type = request.segmentType
            chunk.updated_at = now

        db.commit()
        return {"success": True, "updatedCount": len(chunks)}
    finally:
        db.close()


WORDS_PER_SECOND = 2.5

@app.post("/projects/{project_id}/chunks/{chunk_id}/combine-with-previous")
async def combine_chunk_with_previous(project_id: str, chunk_id: str, request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)
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
async def batch_update_chunks(project_id: str, request: BatchChunkUpdateRequest, req: FastAPIRequest):
    user_id, user_role = _get_user_info(req)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)

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
async def merge_speakers(project_id: str, request: MergeSpeakersRequest, req: FastAPIRequest):
    user_id, user_role = _get_user_info(req)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)

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
async def segment_project(project_id: str, req: FastAPIRequest, request: Optional[SegmentProjectRequest] = None):
    user_id, user_role = _get_user_info(req)
    model = request.model if request else "openai/gpt-4.1-mini"
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)

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


class RechunkSectionRequest(BaseModel):
    model: Optional[str] = None


@app.post("/projects/{project_id}/sections/{section_id}/rechunk")
async def rechunk_section_endpoint(project_id: str, section_id: str, req: FastAPIRequest, request: Optional[RechunkSectionRequest] = None):
    user_id, user_role = _get_user_info(req)
    model = request.model if request and request.model else "openai/gpt-4.1-mini"
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)
    finally:
        db.close()

    try:
        result = await rechunk_section(project_id, section_id, model=model)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Re-chunk failed for section {section_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
async def generate_project_audio(project_id: str, request: GenerateProjectAudioRequest, req: FastAPIRequest):
    user_id, user_role = _get_user_info(req)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)

        tts_engine = project.tts_engine
        narrator_voice_id = project.narrator_voice_id
        base_voice_id = project.base_voice_id
        speakers = json.loads(project.speakers_json) if project.speakers_json else {}
        exaggeration = project.exaggeration
        pause_duration = project.pause_duration
        narrator_emotion = project.narrator_emotion or "auto"
        dialogue_emotion_mode = project.dialogue_emotion_mode or "per-chunk"

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
                    "narratorSpeed": getattr(project, 'narrator_speed', 1.0) or 1.0,
                    "baseVoiceId": base_voice_id,
                    "narratorEmotion": narrator_emotion,
                    "dialogueEmotionMode": dialogue_emotion_mode,
                    "projectId": project_id,
                    "scopeType": "chunk",
                    "scopeId": request.scopeId,
                    "chunkIds": [chunk.id],
                },
                user_id=user_id,
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

            if request.onlyMissing:
                chunks = _filter_missing_chunks(db, project_id, chunks)
                if not chunks:
                    return {"success": True, "message": "All chunks already have audio", "totalSegments": 0}

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
                    "narratorSpeed": getattr(project, 'narrator_speed', 1.0) or 1.0,
                    "baseVoiceId": base_voice_id,
                    "narratorEmotion": narrator_emotion,
                    "dialogueEmotionMode": dialogue_emotion_mode,
                    "projectId": project_id,
                    "scopeType": "section",
                    "scopeId": section.id,
                    "sectionId": section.id,
                    "chapterId": chapter.id,
                    "sectionLabel": section_label,
                    "chapterTitle": chapter_title,
                    "chunkIds": [c.id for c in chunks],
                },
                user_id=user_id,
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

            if request.onlyMissing:
                filtered_sections = []
                for sec, chap, chunks in sections_to_process:
                    remaining = _filter_missing_chunks(db, project_id, chunks)
                    if remaining:
                        filtered_sections.append((sec, chap, remaining))
                sections_to_process = filtered_sections
                if not sections_to_process:
                    return {"success": True, "message": "All chunks already have audio", "totalSegments": 0}

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
                        "narratorSpeed": getattr(project, 'narrator_speed', 1.0) or 1.0,
                        "baseVoiceId": base_voice_id,
                        "narratorEmotion": narrator_emotion,
                        "dialogueEmotionMode": dialogue_emotion_mode,
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
                    user_id=user_id,
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
async def list_project_audio(project_id: str, request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)
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
async def get_project_audio(project_id: str, audio_file_id: str, request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)
        af = db.query(ProjectAudioFile).filter(
            ProjectAudioFile.id == audio_file_id,
            ProjectAudioFile.project_id == project_id
        ).first()
        if not af:
            raise HTTPException(status_code=404, detail="Audio file not found")

        format_map = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "m4b": "audio/x-m4b",
            "zip": "application/zip",
        }
        media_type = format_map.get(af.format, "application/octet-stream")
        headers = {}
        if af.label:
            safe_label = af.label.replace('"', '\\"')
            headers["Content-Disposition"] = f'attachment; filename="{safe_label}"'
        return Response(content=af.audio_data, media_type=media_type, headers=headers)
    finally:
        db.close()


@app.post("/projects/{project_id}/cover")
async def upload_cover_image(project_id: str, request: FastAPIRequest, file: UploadFile = File(...)):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)

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
async def get_cover_image(project_id: str, request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)
        if not project.meta_cover_image:
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
async def delete_cover_image(project_id: str, request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        project = _require_project_access(db, user_id, user_role, project_id)

        project.meta_cover_image = None
        project.updated_at = datetime.utcnow()
        db.commit()
        return {"success": True}
    finally:
        db.close()


def _filter_missing_chunks(db, project_id: str, chunks):
    """Filter chunks to only those that don't have an existing audio file."""
    chunk_ids = [c.id for c in chunks]
    existing_audio = db.query(ProjectAudioFile.scope_id).filter(
        ProjectAudioFile.project_id == project_id,
        ProjectAudioFile.scope_type == "chunk",
        ProjectAudioFile.scope_id.in_(chunk_ids),
    ).all()
    existing_ids = {row.scope_id for row in existing_audio}
    return [c for c in chunks if c.id not in existing_ids]


def _gather_chunk_audio_blobs(db, project_id: str, chunk_ids: list):
    """Gather latest audio blobs for the given chunk IDs, in order."""
    from sqlalchemy import func

    if not chunk_ids:
        return []

    subq = db.query(
        ProjectAudioFile.scope_id,
        func.max(ProjectAudioFile.created_at).label("max_created")
    ).filter(
        ProjectAudioFile.project_id == project_id,
        ProjectAudioFile.scope_type == "chunk",
        ProjectAudioFile.scope_id.in_(chunk_ids),
    ).group_by(ProjectAudioFile.scope_id).subquery()

    latest = db.query(ProjectAudioFile).join(
        subq,
        (ProjectAudioFile.scope_id == subq.c.scope_id) &
        (ProjectAudioFile.created_at == subq.c.max_created)
    ).filter(
        ProjectAudioFile.project_id == project_id,
        ProjectAudioFile.scope_type == "chunk",
    ).all()

    audio_map = {af.scope_id: af.audio_data for af in latest if af.audio_data}
    return [audio_map[cid] for cid in chunk_ids if cid in audio_map]


@app.get("/projects/{project_id}/download")
async def download_project_audio(project_id: str, scope: str = "project", scopeId: str = ""):
    from job_runner import _concatenate_mp3_blobs

    if scope not in ("section", "chapter", "project"):
        raise HTTPException(status_code=400, detail="Invalid scope. Use: section, chapter, project")

    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        pause_ms = int(project.pause_duration) if project.pause_duration else 500
        chunk_ids = []
        filename_label = project.title

        if scope == "section":
            section = db.query(ProjectSection).join(ProjectChapter).filter(
                ProjectSection.id == scopeId,
                ProjectChapter.project_id == project_id
            ).first()
            if not section:
                raise HTTPException(status_code=404, detail="Section not found")
            chapter = db.query(ProjectChapter).filter(ProjectChapter.id == section.chapter_id).first()
            chunks = db.query(ProjectChunk).filter(
                ProjectChunk.section_id == section.id
            ).order_by(ProjectChunk.chunk_index).all()
            chunk_ids = [c.id for c in chunks]
            sec_label = section.title or f"Section {section.section_index + 1}"
            ch_label = chapter.title or f"Chapter {chapter.chapter_index + 1}" if chapter else ""
            filename_label = f"{project.title} - {ch_label} - {sec_label}"

        elif scope == "chapter":
            chapter = db.query(ProjectChapter).filter(
                ProjectChapter.id == scopeId,
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
                chunk_ids.extend([c.id for c in chunks])
            ch_label = chapter.title or f"Chapter {chapter.chapter_index + 1}"
            filename_label = f"{project.title} - {ch_label}"

        elif scope == "project":
            chapters = db.query(ProjectChapter).filter(
                ProjectChapter.project_id == project_id
            ).order_by(ProjectChapter.chapter_index).all()
            for ch in chapters:
                sections = db.query(ProjectSection).filter(
                    ProjectSection.chapter_id == ch.id
                ).order_by(ProjectSection.section_index).all()
                for sec in sections:
                    chunks = db.query(ProjectChunk).filter(
                        ProjectChunk.section_id == sec.id
                    ).order_by(ProjectChunk.chunk_index).all()
                    chunk_ids.extend([c.id for c in chunks])

        blobs = _gather_chunk_audio_blobs(db, project_id, chunk_ids)
        if not blobs:
            raise HTTPException(status_code=400, detail="No audio generated yet for this scope.")

        combined = _concatenate_mp3_blobs(blobs, pause_ms)
        safe_name = "".join(c for c in filename_label if c.isalnum() or c in " _-").strip()

        return Response(
            content=combined,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.mp3"'},
        )
    finally:
        db.close()


@app.get("/projects/{project_id}/audio-stats")
async def get_project_audio_stats(project_id: str):
    """Get counts of chunks with audio at each scope level."""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        all_audio_scope_ids = set(
            row.scope_id for row in db.query(ProjectAudioFile.scope_id).filter(
                ProjectAudioFile.project_id == project_id,
                ProjectAudioFile.scope_type == "chunk",
            ).all()
        )

        stats = {}
        total_chunks = 0
        total_with_audio = 0

        all_chunks = db.query(
            ProjectChunk.id, ProjectChunk.section_id
        ).join(ProjectSection).join(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).all()

        section_chunks = {}
        for cid, sid in all_chunks:
            section_chunks.setdefault(sid, []).append(cid)

        sections = db.query(
            ProjectSection.id, ProjectSection.chapter_id
        ).join(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).all()

        chapter_sections = {}
        for sid, chid in sections:
            chapter_sections.setdefault(chid, []).append(sid)

        chapters = db.query(ProjectChapter.id).filter(
            ProjectChapter.project_id == project_id
        ).all()

        for (ch_id,) in chapters:
            ch_chunks = 0
            ch_audio = 0
            for sec_id in chapter_sections.get(ch_id, []):
                chunk_ids = section_chunks.get(sec_id, [])
                sec_total = len(chunk_ids)
                sec_audio = sum(1 for c in chunk_ids if c in all_audio_scope_ids)
                stats[sec_id] = {"total": sec_total, "withAudio": sec_audio}
                ch_chunks += sec_total
                ch_audio += sec_audio
            stats[ch_id] = {"total": ch_chunks, "withAudio": ch_audio}
            total_chunks += ch_chunks
            total_with_audio += ch_audio

        stats[project_id] = {"total": total_chunks, "withAudio": total_with_audio}

        return stats
    finally:
        db.close()


@app.post("/projects/{project_id}/export")
async def export_project_async(project_id: str, request: FastAPIRequest):
    from export_runner import create_export_job

    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)
    finally:
        db.close()

    body = await request.json()
    export_format = body.get("format", "mp3")
    if export_format not in ("mp3", "mp3-chapters", "m4b"):
        raise HTTPException(status_code=400, detail="Invalid format. Use: mp3, mp3-chapters, m4b")

    job = create_export_job(project_id, export_format, user_id)
    return job


@app.delete("/projects/{project_id}/audio/{audio_file_id}")
async def delete_project_audio(project_id: str, audio_file_id: str, request: FastAPIRequest):
    user_id, user_role = _get_user_info(request)
    db = get_db_session()
    try:
        _require_project_access(db, user_id, user_role, project_id)
        af = db.query(ProjectAudioFile).filter(
            ProjectAudioFile.id == audio_file_id,
            ProjectAudioFile.project_id == project_id
        ).first()
        if not af:
            raise HTTPException(status_code=404, detail="Audio file not found")
        db.delete(af)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
