"""
TTS Job Manager - handles background processing of TTS generation jobs.
Runs TTS generation in background threads and updates progress in the database.
"""
import asyncio
import json
import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import threading

from database import (
    TTSJob, TTSSegment, JobStatus, SegmentStatus, 
    get_db_session, init_database
)

logger = logging.getLogger(__name__)

TTS_OUTPUT_DIR = "/tmp/tts_jobs"
os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)

active_jobs: Dict[str, threading.Thread] = {}
_cancel_tokens: Dict[str, threading.Event] = {}
job_executor = ThreadPoolExecutor(max_workers=4)


def create_job(
    title: str,
    segments: List[Dict[str, Any]],
    config: Dict[str, Any],
    job_group_id: str = None,
    user_id: str = None,
) -> str:
    """Create a new TTS job in the database."""
    db = get_db_session()
    try:
        job_id = str(uuid.uuid4())
        
        job = TTSJob(
            id=job_id,
            title=title,
            status=JobStatus.PENDING.value,
            total_segments=len(segments),
            completed_segments=0,
            failed_segments=0,
            tts_engine=config.get("ttsEngine", "edge-tts"),
            narrator_voice_id=config.get("narratorVoiceId"),
            config_json=json.dumps(config),
            job_group_id=job_group_id,
            user_id=user_id,
        )
        db.add(job)
        
        for idx, seg in enumerate(segments):
            segment = TTSSegment(
                id=str(uuid.uuid4()),
                job_id=job_id,
                segment_index=idx,
                text=seg.get("text", ""),
                segment_type=seg.get("type", "narration"),
                speaker=seg.get("speaker"),
                sentiment=seg.get("sentiment", {}).get("label") if seg.get("sentiment") else None,
                status=SegmentStatus.PENDING.value,
            )
            db.add(segment)
        
        db.commit()
        logger.info(f"Created TTS job {job_id} with {len(segments)} segments")
        return job_id
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create job: {e}")
        raise
    finally:
        db.close()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job status and info."""
    db = get_db_session()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if not job:
            return None
        
        return _serialize_job(job)
    finally:
        db.close()


def _serialize_job(job: TTSJob) -> Dict[str, Any]:
    """Serialize a TTSJob to a dict for API responses."""
    job_type = getattr(job, 'job_type', 'tts') or 'tts'
    progress = (job.completed_segments / job.total_segments * 100) if job.total_segments > 0 else 0
    return {
        "id": job.id,
        "title": job.title,
        "status": job.status,
        "totalSegments": job.total_segments,
        "completedSegments": job.completed_segments,
        "failedSegments": job.failed_segments,
        "ttsEngine": job.tts_engine,
        "narratorVoiceId": job.narrator_voice_id,
        "errorMessage": job.error_message,
        "jobGroupId": job.job_group_id,
        "jobType": job_type,
        "projectId": getattr(job, 'project_id', None),
        "exportFormat": getattr(job, 'export_format', None),
        "outputAudioFileId": getattr(job, 'output_audio_file_id', None),
        "createdAt": job.created_at.isoformat() if job.created_at else None,
        "updatedAt": job.updated_at.isoformat() if job.updated_at else None,
        "progress": progress,
    }


def get_all_jobs(include_completed: bool = True, limit: int = 20, offset: int = 0, user_id: str = None, user_role: str = "user") -> Dict[str, Any]:
    """Get all jobs with pagination, optionally filtering out completed ones."""
    db = get_db_session()
    try:
        query = db.query(TTSJob).order_by(TTSJob.created_at.desc())
        if not include_completed:
            query = query.filter(TTSJob.status.in_([
                JobStatus.PENDING.value,
                JobStatus.WAITING.value,
                JobStatus.PROCESSING.value
            ]))
        if user_id and user_role != "administrator":
            query = query.filter(TTSJob.user_id == user_id)
        
        total = query.count()
        jobs = query.offset(offset).limit(limit).all()
        
        jobs_list = [_serialize_job(job) for job in jobs]
        return {"jobs": jobs_list, "total": total, "limit": limit, "offset": offset}
    finally:
        db.close()


def get_job_segments(job_id: str, completed_only: bool = False) -> List[Dict[str, Any]]:
    """Get segments for a job."""
    db = get_db_session()
    try:
        query = db.query(TTSSegment).filter(TTSSegment.job_id == job_id)
        if completed_only:
            query = query.filter(TTSSegment.status == SegmentStatus.COMPLETED.value)
        segments = query.order_by(TTSSegment.segment_index).all()
        
        return [
            {
                "id": seg.id,
                "segmentIndex": seg.segment_index,
                "text": seg.text,
                "type": seg.segment_type,
                "speaker": seg.speaker,
                "sentiment": seg.sentiment,
                "status": seg.status,
                "audioPath": seg.audio_path,
                "hasAudio": seg.audio_data is not None or seg.audio_path is not None,
                "durationSeconds": seg.duration_seconds,
                "errorMessage": seg.error_message,
            }
            for seg in segments
        ]
    finally:
        db.close()


def get_segment_audio(segment_id: str) -> Optional[bytes]:
    """Get audio data for a segment."""
    db = get_db_session()
    try:
        segment = db.query(TTSSegment).filter(TTSSegment.id == segment_id).first()
        if not segment:
            return None
        
        if segment.audio_data:
            return segment.audio_data
        
        if segment.audio_path and os.path.exists(segment.audio_path):
            with open(segment.audio_path, 'rb') as f:
                return f.read()
        
        return None
    finally:
        db.close()


def update_job_status(job_id: str, status: JobStatus, error_message: str = None):
    """Update job status."""
    db = get_db_session()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if job:
            job.status = status.value
            job.error_message = error_message
            job.updated_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def update_segment_status(
    segment_id: str, 
    status: SegmentStatus, 
    audio_data: bytes = None,
    audio_path: str = None,
    duration_seconds: float = None,
    error_message: str = None
):
    """Update segment status and optionally save audio."""
    db = get_db_session()
    try:
        segment = db.query(TTSSegment).filter(TTSSegment.id == segment_id).first()
        if segment:
            segment.status = status.value
            segment.error_message = error_message
            segment.updated_at = datetime.utcnow()
            
            if audio_data:
                segment.audio_data = audio_data
            if audio_path:
                segment.audio_path = audio_path
            if duration_seconds is not None:
                segment.duration_seconds = duration_seconds
            
            if status == SegmentStatus.COMPLETED:
                job = db.query(TTSJob).filter(TTSJob.id == segment.job_id).first()
                if job:
                    job.completed_segments += 1
                    job.updated_at = datetime.utcnow()
            elif status == SegmentStatus.FAILED:
                job = db.query(TTSJob).filter(TTSJob.id == segment.job_id).first()
                if job:
                    job.failed_segments += 1
                    job.updated_at = datetime.utcnow()
            
            db.commit()
    finally:
        db.close()


def cancel_job(job_id: str) -> bool:
    """Cancel a running or waiting job."""
    from job_runner import remove_job_from_engine_queue
    
    remove_job_from_engine_queue(job_id)
    
    if job_id in _cancel_tokens:
        _cancel_tokens[job_id].set()
    
    if job_id in active_jobs:
        del active_jobs[job_id]
    
    update_job_status(job_id, JobStatus.CANCELLED)
    return True


def delete_job(job_id: str) -> bool:
    """Delete a job and its segments using bulk SQL to avoid loading blobs."""
    cancel_job(job_id)
    
    db = get_db_session()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if not job:
            return False

        export_audio_id = getattr(job, 'output_audio_file_id', None)

        db.query(TTSSegment).filter(TTSSegment.job_id == job_id).delete(synchronize_session=False)

        db.delete(job)

        if export_audio_id:
            from database import ProjectAudioFile
            db.query(ProjectAudioFile).filter(ProjectAudioFile.id == export_audio_id).delete(synchronize_session=False)

        db.commit()

        job_dir = os.path.join(TTS_OUTPUT_DIR, job_id)
        if os.path.exists(job_dir):
            import shutil
            shutil.rmtree(job_dir)

        return True
    finally:
        db.close()


async def cleanup_old_jobs(max_age_hours: int = 24):
    """Clean up jobs older than max_age_hours using bulk deletion."""
    db = get_db_session()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        old_jobs = db.query(TTSJob).filter(TTSJob.created_at < cutoff).all()

        if not old_jobs:
            return

        job_ids = [job.id for job in old_jobs]
        export_audio_ids = [job.output_audio_file_id for job in old_jobs if getattr(job, 'output_audio_file_id', None)]

        db.query(TTSSegment).filter(TTSSegment.job_id.in_(job_ids)).delete(synchronize_session=False)

        for job in old_jobs:
            db.delete(job)

        if export_audio_ids:
            from database import ProjectAudioFile
            db.query(ProjectAudioFile).filter(ProjectAudioFile.id.in_(export_audio_ids)).delete(synchronize_session=False)

        db.commit()

        for jid in job_ids:
            job_dir = os.path.join(TTS_OUTPUT_DIR, jid)
            if os.path.exists(job_dir):
                import shutil
                shutil.rmtree(job_dir, ignore_errors=True)

        logger.info(f"Cleaned up {len(old_jobs)} old jobs")
    finally:
        db.close()


async def run_cleanup_loop():
    """Background task to periodically clean up old jobs."""
    while True:
        await asyncio.sleep(3600)
        try:
            await cleanup_old_jobs()
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
