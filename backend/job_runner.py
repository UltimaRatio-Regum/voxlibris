"""
TTS Job Runner - processes TTS jobs in background threads.
"""
import asyncio
import os
import io
import json
import logging
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from pydub import AudioSegment

from database import JobStatus, SegmentStatus, get_db_session, TTSJob, TTSSegment
from job_manager import (
    update_job_status, update_segment_status, 
    TTS_OUTPUT_DIR, active_jobs
)
from tts_service import TTSService
from audio_processor import AudioProcessor

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=2)


async def process_job(job_id: str):
    """Process a TTS job - generates audio for each segment."""
    logger.info(f"Starting TTS job: {job_id}")
    
    db = get_db_session()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if not job:
            logger.error(f"Job not found: {job_id}")
            return
        
        config = json.loads(job.config_json) if job.config_json else {}
        segments = db.query(TTSSegment).filter(
            TTSSegment.job_id == job_id
        ).order_by(TTSSegment.segment_index).all()
        
        segment_data = [
            {
                "id": s.id,
                "text": s.text,
                "type": s.segment_type,
                "speaker": s.speaker,
                "sentiment": {"label": s.sentiment, "score": 0.8} if s.sentiment else None,
            }
            for s in segments
        ]
    finally:
        db.close()
    
    update_job_status(job_id, JobStatus.PROCESSING)
    
    job_dir = os.path.join(TTS_OUTPUT_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    tts_service = TTSService()
    audio_processor = AudioProcessor()
    
    tts_engine = config.get("ttsEngine", "edge-tts")
    narrator_voice_id = config.get("narratorVoiceId")
    speakers = config.get("speakers", {})
    exaggeration = config.get("defaultExaggeration", 0.5)
    
    all_succeeded = True
    
    for seg_data in segment_data:
        segment_id = seg_data["id"]
        
        if job_id not in active_jobs:
            logger.info(f"Job {job_id} was cancelled")
            return
        
        try:
            update_segment_status(segment_id, SegmentStatus.PROCESSING)
            
            voice_id = narrator_voice_id
            if seg_data.get("speaker") and seg_data["speaker"] in speakers:
                speaker_config = speakers[seg_data["speaker"]]
                if speaker_config.get("voiceSampleId"):
                    voice_id = speaker_config["voiceSampleId"]
            
            audio = await generate_segment_audio(
                tts_service=tts_service,
                text=seg_data["text"],
                tts_engine=tts_engine,
                voice_id=voice_id,
                sentiment=seg_data.get("sentiment"),
                exaggeration=exaggeration,
            )
            
            if audio is None or len(audio) == 0:
                raise RuntimeError("TTS returned empty audio")
            
            if seg_data.get("sentiment") and seg_data["sentiment"].get("label"):
                audio = audio_processor.apply_emotion_prosody(
                    audio,
                    tts_service.sample_rate,
                    seg_data["sentiment"]["label"],
                    seg_data["sentiment"].get("score", 0.8),
                )
            
            mp3_data = convert_to_mp3(audio, tts_service.sample_rate)
            
            audio_path = os.path.join(job_dir, f"segment_{seg_data['id']}.mp3")
            with open(audio_path, 'wb') as f:
                f.write(mp3_data)
            
            duration = len(audio) / tts_service.sample_rate
            
            update_segment_status(
                segment_id,
                SegmentStatus.COMPLETED,
                audio_data=mp3_data,
                audio_path=audio_path,
                duration_seconds=duration,
            )
            
            logger.info(f"Completed segment {segment_id} ({duration:.2f}s)")
            
        except asyncio.CancelledError:
            logger.info(f"Job {job_id} cancelled during segment {segment_id}")
            update_segment_status(segment_id, SegmentStatus.FAILED, error_message="Job cancelled")
            return
        except Exception as e:
            logger.error(f"Failed to process segment {segment_id}: {e}")
            update_segment_status(segment_id, SegmentStatus.FAILED, error_message=str(e))
            all_succeeded = False
    
    if all_succeeded:
        update_job_status(job_id, JobStatus.COMPLETED)
        logger.info(f"Job {job_id} completed successfully")
    else:
        update_job_status(job_id, JobStatus.COMPLETED, error_message="Some segments failed")
        logger.warning(f"Job {job_id} completed with some failures")
    
    if job_id in active_jobs:
        del active_jobs[job_id]


async def generate_segment_audio(
    tts_service: TTSService,
    text: str,
    tts_engine: str,
    voice_id: str = None,
    sentiment: Dict[str, Any] = None,
    exaggeration: float = 0.5,
) -> np.ndarray:
    """Generate audio for a single segment."""
    
    voice_path = None
    if voice_id and voice_id.startswith("library:"):
        voice_path = get_library_voice_path(voice_id[8:])
    elif voice_id and not voice_id.startswith("edge:") and not voice_id.startswith("openai:"):
        voice_path = get_uploaded_voice_path(voice_id)
    
    edge_voice = None
    if voice_id and voice_id.startswith("edge:"):
        edge_voice = voice_id[5:]
    
    openai_voice = None
    if voice_id and voice_id.startswith("openai:"):
        openai_voice = voice_id[7:]
    
    if tts_engine == "edge-tts":
        return await tts_service._generate_with_edge_tts(text, edge_voice or "en-US-AriaNeural")
    
    elif tts_engine == "openai":
        return await tts_service._generate_with_openai(text, openai_voice or "alloy")
    
    elif tts_engine == "chatterbox-free":
        if not voice_path:
            raise ValueError("Chatterbox requires a voice sample")
        return await tts_service._generate_with_chatterbox_gradio(text, voice_path, exaggeration)
    
    elif tts_engine == "chatterbox-paid":
        if not voice_path:
            raise ValueError("Chatterbox requires a voice sample")
        return await tts_service._generate_with_chatterbox_paid(text, voice_path, exaggeration)
    
    elif tts_engine == "soprano":
        return await tts_service._generate_with_soprano(text)
    
    elif tts_engine == "piper":
        return await tts_service._generate_with_piper(text)
    
    else:
        return await tts_service._generate_with_edge_tts(text, "en-US-AriaNeural")


def get_library_voice_path(voice_id: str) -> str:
    """Get file path for a library voice."""
    voice_samples_dir = os.path.join(os.path.dirname(__file__), "..", "voice_samples")
    mic1_path = os.path.join(voice_samples_dir, f"{voice_id}_mic1.wav")
    mic2_path = os.path.join(voice_samples_dir, f"{voice_id}_mic2.wav")
    
    if os.path.exists(mic1_path):
        return mic1_path
    if os.path.exists(mic2_path):
        return mic2_path
    
    raise FileNotFoundError(f"Voice file not found: {voice_id}")


def get_uploaded_voice_path(voice_id: str) -> str:
    """Get file path for an uploaded voice sample."""
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    for ext in ['.wav', '.mp3', '.ogg', '.flac']:
        path = os.path.join(uploads_dir, f"{voice_id}{ext}")
        if os.path.exists(path):
            return path
    
    raise FileNotFoundError(f"Uploaded voice not found: {voice_id}")


def convert_to_mp3(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convert numpy audio array to MP3 bytes."""
    audio_int16 = (audio * 32767).astype(np.int16)
    
    audio_segment = AudioSegment(
        audio_int16.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1
    )
    
    buffer = io.BytesIO()
    audio_segment.export(buffer, format="mp3", bitrate="192k")
    return buffer.getvalue()


def start_job_async(job_id: str):
    """Start processing a job in the background."""
    async def run():
        try:
            await process_job(job_id)
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            update_job_status(job_id, JobStatus.FAILED, error_message=str(e))
    
    loop = asyncio.get_event_loop()
    task = loop.create_task(run())
    active_jobs[job_id] = task
    return task
