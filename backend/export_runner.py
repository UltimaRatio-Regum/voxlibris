import io
import logging
import math
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from database import (
    JobStatus, get_db_session, TTSJob, ProjectAudioFile,
    ProjectChapter, ProjectSection, ProjectChunk, Project
)
from audio_export import export_single_mp3, export_mp3_per_chapter, export_m4b

logger = logging.getLogger(__name__)

_export_executor = ThreadPoolExecutor(max_workers=2)


def create_export_job(project_id: str, export_format: str, user_id: str) -> dict:
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("Project not found")

        job_id = str(uuid.uuid4())
        fmt_label = {"mp3": "MP3", "mp3-chapters": "MP3 (per chapter)", "m4b": "M4B"}.get(export_format, export_format.upper())
        job = TTSJob(
            id=job_id,
            title=f"Export: {project.title} [{fmt_label}]",
            status=JobStatus.PENDING.value,
            total_segments=0,
            completed_segments=0,
            failed_segments=0,
            tts_engine="export",
            job_type="export",
            project_id=project_id,
            export_format=export_format,
            user_id=user_id,
        )
        db.add(job)
        db.commit()

        from job_manager import _serialize_job
        result = _serialize_job(job)
    finally:
        db.close()

    _export_executor.submit(_run_export, job_id)
    return result


def _set_progress(job, db, total_chunks: int, pct: float, message: str):
    job.total_segments = total_chunks
    job.completed_segments = round(pct * total_chunks)
    job.error_message = message
    job.updated_at = datetime.utcnow()
    try:
        db.commit()
    except Exception as exc:
        logger.debug(f"Export progress commit failed: {exc}")


def _run_export(job_id: str):
    db = get_db_session()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if not job:
            return

        job.status = JobStatus.PROCESSING.value
        job.updated_at = datetime.utcnow()
        db.commit()

        project = db.query(Project).filter(Project.id == job.project_id).first()
        if not project:
            job.status = JobStatus.FAILED.value
            job.error_message = "Project not found"
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        chapters = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project.id
        ).order_by(ProjectChapter.chapter_index).all()

        total_chunk_count = 0
        chapter_chunk_ids = []
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
            chapter_chunk_ids.append((ch.title or f"Chapter {ch.chapter_index + 1}", chunk_ids))
            total_chunk_count += len(chunk_ids)

        _set_progress(job, db, total_chunk_count, 0.0, f"Gathering chunks from DB (0 of {total_chunk_count})...")

        chapter_audio = []
        gathered_count = 0
        for ch_title, chunk_ids in chapter_chunk_ids:
            blobs = []
            for cid in chunk_ids:
                af = db.query(ProjectAudioFile).filter(
                    ProjectAudioFile.project_id == project.id,
                    ProjectAudioFile.scope_type == "chunk",
                    ProjectAudioFile.scope_id == cid,
                ).order_by(ProjectAudioFile.created_at.desc()).first()
                if af and af.audio_data:
                    blobs.append(af.audio_data)

                gathered_count += 1
                pct = (gathered_count / max(total_chunk_count, 1)) * 0.15
                _set_progress(job, db, total_chunk_count, pct, f"Gathering chunks from DB ({gathered_count} of {total_chunk_count})...")

            chapter_audio.append((ch_title, blobs))

        total_blobs = sum(len(blobs) for _, blobs in chapter_audio)
        if total_blobs == 0:
            job.status = JobStatus.FAILED.value
            job.error_message = "No audio generated yet. Generate audio before exporting."
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        total_merge_levels = max(1, math.ceil(math.log2(max(total_blobs, 1))))

        _set_progress(job, db, total_chunk_count, 0.15, f"Decoding chunks for processing (0 of {total_blobs})...")

        def _export_progress(phase: str, current: int, total: int, message: str):
            if phase == "decode":
                pct = 0.15 + (current / max(total, 1)) * 0.45
            elif phase == "merge":
                pct = 0.60 + (current / max(total, 1)) * 0.15
            elif phase == "encode":
                pct = 0.75 + (current / max(total, 1)) * 0.25
            else:
                pct = 0.0
            _set_progress(job, db, total_chunk_count, min(pct, 1.0), message)

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
            progress_callback=_export_progress,
        )

        export_format = job.export_format or "mp3"

        if export_format == "mp3":
            data = export_single_mp3(**kwargs)
            scope_format = "mp3"
            label = f"{project.title}.mp3"
        elif export_format == "mp3-chapters":
            data = export_mp3_per_chapter(**kwargs)
            scope_format = "zip"
            label = f"{project.title} - Chapters.zip"
        elif export_format == "m4b":
            data = export_m4b(**kwargs)
            scope_format = "m4b"
            label = f"{project.title}.m4b"
        else:
            job.status = JobStatus.FAILED.value
            job.error_message = f"Unknown export format: {export_format}"
            job.updated_at = datetime.utcnow()
            db.commit()
            return

        audio_file = ProjectAudioFile(
            id=str(uuid.uuid4()),
            project_id=project.id,
            scope_type="export",
            scope_id=project.id,
            format=scope_format,
            audio_data=data,
            label=label,
            tts_engine="export",
            created_at=datetime.utcnow(),
        )
        db.add(audio_file)

        job.output_audio_file_id = audio_file.id
        job.status = JobStatus.COMPLETED.value
        job.completed_segments = total_chunk_count
        job.total_segments = total_chunk_count
        job.error_message = None
        job.updated_at = datetime.utcnow()
        db.commit()

        logger.info(f"Export job {job_id} completed: {label} ({len(data)} bytes)")

    except Exception as e:
        logger.exception(f"Export job {job_id} failed: {e}")
        try:
            job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)[:500]
                job.updated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
