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
    
    def fallback_parse_chunk(chunk: str) -> dict:
        """Use basic text parser as fallback when LLM fails."""
        segments_list, speakers_list = text_parser.parse(chunk)
        segments = []
        for seg in segments_list:
            segments.append({
                "type": seg.type,
                "text": seg.text,
                "speaker": seg.speaker,
                "sentiment": seg.sentiment.label if seg.sentiment else "neutral",
            })
        return {"segments": segments, "detectedSpeakers": speakers_list, "fallback": True}
    
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
        """Call LLM to parse a chunk of text."""
        speaker_hint = ""
        if known_speakers:
            speaker_hint = f"Known speakers so far: {', '.join(known_speakers)}. "
        
        valid_sentiments = ["neutral", "happy", "sad", "angry", "fearful", "excited", "calm", "surprised", "anxious", "hopeful", "melancholy", "disgusted"]
        
        prompt = f"""Analyze this text excerpt and identify dialogue vs narration. For each dialogue segment, identify the speaker.

{speaker_hint}Previous context: {context[:500] if context else 'Start of text'}

TEXT TO ANALYZE:
{chunk}

Return a JSON object with this structure:
{{
  "segments": [
    {{
      "type": "narration" or "dialogue",
      "text": "the actual text",
      "speaker": "speaker name or null for narration",
      "sentiment": one of {valid_sentiments}
    }}
  ],
  "detectedSpeakers": ["list", "of", "speaker", "names"]
}}

Be precise about separating quoted dialogue from narration. Return ONLY valid JSON."""

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
                return fallback_parse_chunk(chunk)
            
            if not result.get("segments"):
                logger.warning(f"LLM returned empty segments, using fallback parser")
                return fallback_parse_chunk(chunk)
            
            return result
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}")
            return fallback_parse_chunk(chunk)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return fallback_parse_chunk(chunk)
    
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
                        segment = {
                            "id": str(uuid.uuid4()),
                            "type": seg.get("type", "narration"),
                            "text": seg.get("text", ""),
                            "speaker": seg.get("speaker"),
                            "speakerCandidates": {seg.get("speaker"): 0.9} if seg.get("speaker") else None,
                            "needsReview": False,
                            "sentiment": {"label": seg.get("sentiment", "neutral"), "score": 0.8},
                            "startIndex": 0,
                            "endIndex": len(seg.get("text", "")),
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
    
    prompt = f"""Analyze this text and identify dialogue vs narration. For each dialogue segment, identify the speaker.

TEXT:
{request.text[:8000]}

Return a JSON object with:
{{
  "segments": [
    {{"type": "narration" or "dialogue", "text": "...", "speaker": "name or null", "sentiment": "neutral/happy/sad/angry"}}
  ],
  "detectedSpeakers": ["list", "of", "names"]
}}

Return ONLY valid JSON."""

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
                    "messages": [{"role": "user", "content": prompt}],
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
                segments.append({
                    "id": str(uuid.uuid4()),
                    "type": seg.get("type", "narration"),
                    "text": seg.get("text", ""),
                    "speaker": seg.get("speaker"),
                    "speakerCandidates": {seg.get("speaker"): 0.9} if seg.get("speaker") else None,
                    "needsReview": False,
                    "sentiment": {"label": seg.get("sentiment", "neutral"), "score": 0.8},
                    "startIndex": 0,
                    "endIndex": len(seg.get("text", "")),
                })
            
            return {
                "segments": segments,
                "detectedSpeakers": result.get("detectedSpeakers", []),
            }
    except Exception as e:
        logger.error(f"LLM parse failed: {e}")
        segments, speakers = text_parser.parse(request.text)
        return ParseTextResponse(segments=segments, detectedSpeakers=speakers)


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
            
            voice_files = {}
            
            # Add uploaded voice samples
            for voice_id, sample in voice_samples.items():
                voice_files[voice_id] = str(UPLOAD_DIR / sample.audioUrl.lstrip("/uploads/"))
            
            # Add library voices (with library: prefix)
            if VOICE_LIBRARY_DIR.exists():
                for wav_file in VOICE_LIBRARY_DIR.glob("*_mic1.wav"):
                    voice_id = wav_file.stem.replace("_mic1", "")
                    voice_files[f"library:{voice_id}"] = str(wav_file)
            
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
    """Run cleanup loop on startup."""
    import asyncio
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
