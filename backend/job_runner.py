"""
TTS Job Runner - processes TTS jobs in background threads.
Per-engine mutex ensures only one job runs per TTS engine at a time.
"""
import asyncio
import os
import io
import json
import logging
import threading
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, Counter

import numpy as np
from pydub import AudioSegment

from database import JobStatus, SegmentStatus, get_db_session, TTSJob, TTSSegment, CustomVoice, TTSEngineEndpoint, VoiceLibraryEntry, ProjectAudioFile
from job_manager import (
    update_job_status, update_segment_status, 
    TTS_OUTPUT_DIR, active_jobs, _cancel_tokens
)
from tts_service import TTSService
from audio_processor import AudioProcessor
from remote_tts_client import RemoteTTSClient, TTSRequest

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=2)

_engine_guard = threading.Lock()
_engine_busy: Dict[str, bool] = {}
_engine_queues: Dict[str, List[str]] = defaultdict(list)


def _start_next_for_engine(engine: str):
    with _engine_guard:
        queue = _engine_queues.get(engine, [])
        while queue:
            next_job_id = queue.pop(0)
            db = get_db_session()
            try:
                job = db.query(TTSJob).filter(TTSJob.id == next_job_id).first()
                if not job or job.status != JobStatus.WAITING.value:
                    continue
            finally:
                db.close()
            _engine_busy[engine] = True
            _launch_job_thread(next_job_id, engine)
            return
        _engine_busy[engine] = False


def _apply_emotion_smoothing(segment_data: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply narrator emotion override and dialogue emotion flattening to segments."""
    narrator_emotion = config.get("narratorEmotion", "auto")
    dialogue_mode = config.get("dialogueEmotionMode", "per-chunk")

    if narrator_emotion != "auto":
        for seg in segment_data:
            if seg.get("type") == "narration":
                existing = seg.get("sentiment") or {}
                seg["sentiment"] = {"label": narrator_emotion, "score": existing.get("score", 0.8)}

    if dialogue_mode != "per-chunk":
        i = 0
        while i < len(segment_data):
            seg = segment_data[i]
            if seg.get("type") != "dialogue" or not seg.get("speaker"):
                i += 1
                continue
            speaker = seg["speaker"]
            group_start = i
            j = i + 1
            while j < len(segment_data):
                next_seg = segment_data[j]
                if next_seg.get("type") == "dialogue" and next_seg.get("speaker") == speaker:
                    j += 1
                else:
                    break
            group_end = j

            if group_end - group_start > 1:
                if dialogue_mode == "first-chunk":
                    first_sent = segment_data[group_start].get("sentiment") or {}
                    first_emotion = first_sent.get("label", "neutral")
                    for k in range(group_start, group_end):
                        seg_sent = segment_data[k].get("sentiment") or {}
                        segment_data[k]["sentiment"] = {"label": first_emotion, "score": seg_sent.get("score", 0.8)}
                elif dialogue_mode == "word-count-majority":
                    emotion_words: Counter = Counter()
                    for k in range(group_start, group_end):
                        seg_sent = segment_data[k].get("sentiment") or {}
                        emotion = seg_sent.get("label", "neutral")
                        word_count = len(segment_data[k].get("text", "").split())
                        emotion_words[emotion] += word_count
                    dominant_emotion = emotion_words.most_common(1)[0][0] if emotion_words else "neutral"
                    for k in range(group_start, group_end):
                        seg_sent = segment_data[k].get("sentiment") or {}
                        segment_data[k]["sentiment"] = {"label": dominant_emotion, "score": seg_sent.get("score", 0.8)}

            i = group_end

    return segment_data


async def process_job(job_id: str, cancel_token: threading.Event = None):
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
    
    segment_data = _apply_emotion_smoothing(segment_data, config)

    tts_engine = config.get("ttsEngine", "edge-tts")
    narrator_voice_id = config.get("narratorVoiceId")
    narrator_speed = config.get("narratorSpeed", 1.0) or 1.0
    base_voice_id = config.get("baseVoiceId")
    speakers = config.get("speakers", {})
    exaggeration = config.get("defaultExaggeration", 0.5)

    remote_client = get_remote_engine(tts_engine)
    if remote_client:
        update_job_status(job_id, JobStatus.PROCESSING, error_message="Waking up TTS engine (may take a few minutes if the Space is sleeping)...")
        try:
            await remote_client.wake_up(
                timeout=300.0,
                is_cancelled=lambda: cancel_token is not None and cancel_token.is_set(),
            )
            logger.info(f"Remote engine {tts_engine} is ready for job {job_id}")
        except asyncio.CancelledError:
            logger.info(f"Job {job_id} cancelled during engine wake-up")
            update_job_status(job_id, JobStatus.FAILED, error_message="Job cancelled during engine wake-up")
            return
        except TimeoutError as e:
            logger.error(f"Remote engine {tts_engine} failed to wake up: {e}")
            update_job_status(job_id, JobStatus.FAILED, error_message=f"TTS engine failed to start: {e}")
            return
        except Exception as e:
            logger.error(f"Error waking remote engine {tts_engine}: {e}")
            update_job_status(job_id, JobStatus.FAILED, error_message=f"TTS engine failed to start: {e}")
            return

    update_job_status(job_id, JobStatus.PROCESSING)
    
    job_dir = os.path.join(TTS_OUTPUT_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    
    tts_service = TTSService()
    audio_processor = AudioProcessor()
    
    voice_path_cache: Dict[str, str] = {}
    temp_files: List[str] = []
    all_succeeded = True
    
    try:
        for seg_data in segment_data:
            segment_id = seg_data["id"]
            
            if cancel_token is not None and cancel_token.is_set():
                logger.info(f"Job {job_id} was cancelled (token set)")
                update_job_status(job_id, JobStatus.CANCELLED)
                return
            
            try:
                update_segment_status(segment_id, SegmentStatus.PROCESSING)
                
                voice_id = narrator_voice_id
                speed_factor = narrator_speed
                pitch_offset = 0.0
                if seg_data.get("speaker") and seg_data["speaker"] in speakers:
                    speaker_config = speakers[seg_data["speaker"]]
                    if speaker_config.get("voiceSampleId"):
                        voice_id = speaker_config["voiceSampleId"]
                    speed_factor = speaker_config.get("speedFactor", 1.0) or 1.0
                    pitch_offset = speaker_config.get("pitchOffset", 0.0) or 0.0
                
                audio = await generate_segment_audio(
                    tts_service=tts_service,
                    text=seg_data["text"],
                    tts_engine=tts_engine,
                    voice_id=voice_id,
                    base_voice_id=base_voice_id,
                    sentiment=seg_data.get("sentiment"),
                    exaggeration=exaggeration,
                    voice_path_cache=voice_path_cache,
                    temp_files=temp_files,
                )
                
                if audio is None or len(audio) == 0:
                    raise RuntimeError("TTS returned empty audio")
                
                if abs(speed_factor - 1.0) > 0.01 or abs(pitch_offset) > 0.01:
                    audio = audio_processor.apply_time_stretch(audio, tts_service.sample_rate, speed_factor) if abs(speed_factor - 1.0) > 0.01 else audio
                    audio = audio_processor.apply_pitch_shift(audio, tts_service.sample_rate, pitch_offset) if abs(pitch_offset) > 0.01 else audio
                
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
                update_job_status(job_id, JobStatus.CANCELLED)
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
        
        _persist_project_audio(job_id, config, tts_engine, narrator_voice_id)
    finally:
        for tmp_path in temp_files:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        
        active_jobs.pop(job_id, None)


def _persist_project_audio(job_id: str, config: Dict[str, Any], tts_engine: str, narrator_voice_id: str):
    """After a job completes, persist completed segment audio to ProjectAudioFile.
    
    For section-scoped jobs: persists chunk audio + creates a combined section-level entry.
    Then checks if all sibling section jobs in a group are complete to create chapter-level entries.
    """
    project_id = config.get("projectId")
    if not project_id:
        return
    
    scope_type = config.get("scopeType", "chunk")
    scope_id = config.get("scopeId", "")
    
    try:
        import uuid as uuid_mod
        from datetime import datetime
        
        db = get_db_session()
        try:
            segments = db.query(TTSSegment).filter(
                TTSSegment.job_id == job_id,
                TTSSegment.status == SegmentStatus.COMPLETED.value,
            ).order_by(TTSSegment.segment_index).all()
            
            if not segments:
                logger.warning(f"No completed segments for project audio persistence (job {job_id})")
                return
            
            chunk_ids = config.get("chunkIds", [])
            
            for seg in segments:
                if not seg.audio_data:
                    continue
                
                if seg.segment_index < len(chunk_ids):
                    chunk_scope_id = chunk_ids[seg.segment_index]
                else:
                    chunk_scope_id = seg.id
                
                af = ProjectAudioFile(
                    id=str(uuid_mod.uuid4()),
                    project_id=project_id,
                    scope_type="chunk",
                    scope_id=chunk_scope_id,
                    audio_data=seg.audio_data,
                    format="mp3",
                    duration_seconds=seg.duration_seconds,
                    tts_engine=tts_engine,
                    voice_id=narrator_voice_id,
                    settings_json=json.dumps({
                        "ttsEngine": tts_engine,
                        "narratorVoiceId": narrator_voice_id,
                        "exaggeration": config.get("defaultExaggeration", 0.5),
                        "speaker": seg.speaker,
                        "sentiment": seg.sentiment,
                    }),
                    created_at=datetime.utcnow(),
                )
                db.add(af)
            
            db.commit()
            logger.info(f"Persisted {len(segments)} chunk audio files for project {project_id}")
            
            if scope_type == "section":
                _create_section_combined_audio(db, job_id, config, project_id, tts_engine, narrator_voice_id)
                
                job_group_id = config.get("jobGroupId")
                if job_group_id:
                    _check_and_create_chapter_audio(db, job_group_id, config, project_id, tts_engine, narrator_voice_id)
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to persist project audio: {e}")
            import traceback
            traceback.print_exc()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in _persist_project_audio: {e}")


def _get_latest_chunk_audio(db, project_id: str, chunk_ids: list) -> dict:
    """Get the latest audio blob for each chunk, keyed by chunk ID."""
    from sqlalchemy import func
    
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
    
    return {af.scope_id: af for af in latest}


def _create_section_combined_audio(db, job_id: str, config: Dict[str, Any], project_id: str, tts_engine: str, narrator_voice_id: str):
    """Concatenate chunk audio into a single section-level ProjectAudioFile."""
    import uuid as uuid_mod
    from datetime import datetime
    
    section_id = config.get("sectionId") or config.get("scopeId", "")
    section_label = config.get("sectionLabel", "Section")
    chapter_title = config.get("chapterTitle", "")
    pause_ms = config.get("pauseBetweenSegments", 500)
    
    chunk_ids = config.get("chunkIds", [])
    if not chunk_ids:
        return
    
    chunk_audio_map = _get_latest_chunk_audio(db, project_id, chunk_ids)
    ordered_blobs = []
    for cid in chunk_ids:
        if cid in chunk_audio_map and chunk_audio_map[cid].audio_data:
            ordered_blobs.append(chunk_audio_map[cid].audio_data)
    
    if not ordered_blobs:
        logger.warning(f"No chunk audio found for section {section_id}")
        return
    
    combined_mp3 = _concatenate_mp3_blobs(ordered_blobs, pause_ms)
    duration = _get_mp3_duration(combined_mp3)
    
    label = f"{chapter_title} — {section_label}" if chapter_title else section_label
    
    existing = db.query(ProjectAudioFile).filter(
        ProjectAudioFile.project_id == project_id,
        ProjectAudioFile.scope_type == "section",
        ProjectAudioFile.scope_id == section_id,
    ).with_for_update().first()
    if existing:
        existing.audio_data = combined_mp3
        existing.duration_seconds = duration
        existing.tts_engine = tts_engine
        existing.voice_id = narrator_voice_id
        existing.label = label
        existing.created_at = datetime.utcnow()
    else:
        af = ProjectAudioFile(
            id=str(uuid_mod.uuid4()),
            project_id=project_id,
            scope_type="section",
            scope_id=section_id,
            audio_data=combined_mp3,
            format="mp3",
            duration_seconds=duration,
            tts_engine=tts_engine,
            voice_id=narrator_voice_id,
            label=label,
            settings_json=json.dumps({"ttsEngine": tts_engine, "narratorVoiceId": narrator_voice_id}),
            created_at=datetime.utcnow(),
        )
        db.add(af)
    
    db.commit()
    logger.info(f"Created section-level combined audio for section {section_id} ({label})")


def _check_and_create_chapter_audio(db, job_group_id: str, config: Dict[str, Any], project_id: str, tts_engine: str, narrator_voice_id: str):
    """Check if all section jobs for this chapter are done, then create chapter-level combined audio.
    
    Uses per-chapter completion checking: only creates chapter audio when all sections
    of that specific chapter have section-level audio, regardless of other chapters in the group.
    """
    import uuid as uuid_mod
    from datetime import datetime
    from database import ProjectChapter, ProjectSection
    
    chapter_id = config.get("chapterId")
    if not chapter_id:
        return
    
    pause_ms = config.get("pauseBetweenSegments", 500)
    
    chapter = db.query(ProjectChapter).filter(ProjectChapter.id == chapter_id).first()
    if not chapter:
        return
    
    sections = db.query(ProjectSection).filter(
        ProjectSection.chapter_id == chapter_id
    ).order_by(ProjectSection.section_index).all()
    
    if not sections:
        return
    
    section_ids = [s.id for s in sections]
    section_audios = db.query(ProjectAudioFile).filter(
        ProjectAudioFile.project_id == project_id,
        ProjectAudioFile.scope_type == "section",
        ProjectAudioFile.scope_id.in_(section_ids),
    ).all()
    
    section_audio_map = {af.scope_id: af for af in section_audios}
    
    if len(section_audio_map) < len(section_ids):
        return
    
    ordered_blobs = []
    for sid in section_ids:
        if sid in section_audio_map and section_audio_map[sid].audio_data:
            ordered_blobs.append(section_audio_map[sid].audio_data)
        else:
            return
    
    combined_mp3 = _concatenate_mp3_blobs(ordered_blobs, pause_ms * 2)
    duration = _get_mp3_duration(combined_mp3)
    
    chapter_title = chapter.title or f"Chapter {chapter.chapter_index + 1}"
    
    existing = db.query(ProjectAudioFile).filter(
        ProjectAudioFile.project_id == project_id,
        ProjectAudioFile.scope_type == "chapter",
        ProjectAudioFile.scope_id == chapter_id,
    ).with_for_update().first()
    if existing:
        existing.audio_data = combined_mp3
        existing.duration_seconds = duration
        existing.tts_engine = tts_engine
        existing.voice_id = narrator_voice_id
        existing.label = chapter_title
        existing.created_at = datetime.utcnow()
    else:
        af = ProjectAudioFile(
            id=str(uuid_mod.uuid4()),
            project_id=project_id,
            scope_type="chapter",
            scope_id=chapter_id,
            audio_data=combined_mp3,
            format="mp3",
            duration_seconds=duration,
            tts_engine=tts_engine,
            voice_id=narrator_voice_id,
            label=chapter_title,
            settings_json=json.dumps({"ttsEngine": tts_engine, "narratorVoiceId": narrator_voice_id}),
            created_at=datetime.utcnow(),
        )
        db.add(af)
    
    db.commit()
    logger.info(f"Created chapter-level combined audio for chapter {chapter_id} ({chapter_title})")


def _concatenate_mp3_blobs(mp3_blobs: List[bytes], pause_ms: int = 500) -> bytes:
    """Concatenate multiple MP3 byte blobs into a single MP3 with pauses between them.
    Uses pairwise merge for O(N log N) total bytes written instead of O(N^2)."""
    pause = AudioSegment.silent(duration=pause_ms) if pause_ms > 0 else None
    
    segments = []
    for i, blob in enumerate(mp3_blobs):
        seg = AudioSegment.from_mp3(io.BytesIO(blob))
        if i > 0 and pause:
            segments.append(pause)
        segments.append(seg)
    
    if not segments:
        combined = AudioSegment.empty()
    elif len(segments) == 1:
        combined = segments[0]
    else:
        while len(segments) > 1:
            merged = []
            idx = 0
            remaining = len(segments)
            while idx < remaining:
                if remaining - idx == 3:
                    merged.append(segments[idx] + segments[idx + 1] + segments[idx + 2])
                    idx += 3
                elif remaining - idx >= 2:
                    merged.append(segments[idx] + segments[idx + 1])
                    idx += 2
                else:
                    merged.append(segments[idx])
                    idx += 1
            segments = merged
        combined = segments[0]
    
    buffer = io.BytesIO()
    combined.export(buffer, format="mp3", bitrate="192k")
    return buffer.getvalue()


def _get_mp3_duration(mp3_data: bytes) -> float:
    """Get duration in seconds from MP3 bytes."""
    try:
        seg = AudioSegment.from_mp3(io.BytesIO(mp3_data))
        return len(seg) / 1000.0
    except Exception:
        return 0.0


async def generate_segment_audio(
    tts_service: TTSService,
    text: str,
    tts_engine: str,
    voice_id: str = None,
    base_voice_id: str = None,
    sentiment: Dict[str, Any] = None,
    exaggeration: float = 0.5,
    voice_path_cache: Dict[str, str] = None,
    temp_files: List[str] = None,
) -> np.ndarray:
    """Generate audio for a single segment."""
    import soundfile as sf
    
    if voice_path_cache is None:
        voice_path_cache = {}
    if temp_files is None:
        temp_files = []
    
    voice_path = None
    remote_builtin_voice = None
    if voice_id and voice_id.startswith("library:"):
        if voice_id in voice_path_cache:
            voice_path = voice_path_cache[voice_id]
        else:
            voice_path = get_library_voice_path(voice_id[8:])
            voice_path_cache[voice_id] = voice_path
            if not voice_path.startswith(os.path.join(os.path.dirname(__file__), "..")):
                temp_files.append(voice_path)
    elif voice_id and voice_id.startswith("remote:"):
        remote_builtin_voice = voice_id[7:]
    elif voice_id and not voice_id.startswith("edge:") and not voice_id.startswith("openai:"):
        if voice_id in voice_path_cache:
            voice_path = voice_path_cache[voice_id]
        else:
            voice_path = get_uploaded_voice_path(voice_id)
            voice_path_cache[voice_id] = voice_path
            if "/uploads/" not in voice_path:
                temp_files.append(voice_path)
    
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
        remote_client = get_remote_engine(tts_engine)
        if remote_client:
            voice_bytes = None
            if voice_path:
                with open(voice_path, "rb") as f:
                    voice_bytes = f.read()
            
            emotion_set = ["neutral"]
            if sentiment and sentiment.get("label"):
                emotion_set = [sentiment["label"]]
            
            tts_req = TTSRequest(
                input_text=text,
                builtin_voice_id=remote_builtin_voice,
                base_voice_id=base_voice_id,
                voice_to_clone_sample=voice_bytes,
                emotion_set=emotion_set,
                intensity=int(exaggeration * 100),
            )
            
            wav_bytes = await remote_client.convert_text_to_speech(tts_req)
            
            audio_buf = io.BytesIO(wav_bytes)
            audio_data, sr = sf.read(audio_buf, dtype="float32")
            if len(audio_data.shape) > 1:
                audio_data = audio_data[:, 0]
            if sr != tts_service.sample_rate:
                import scipy.signal
                num_samples = int(len(audio_data) * tts_service.sample_rate / sr)
                audio_data = scipy.signal.resample(audio_data, num_samples)
            return audio_data
        
        raise ValueError(f"Unknown TTS engine: {tts_engine}. Make sure the engine is registered in Settings.")


def get_remote_engine(engine_id: str):
    """Look up a registered remote TTS engine from the DB."""
    db = get_db_session()
    try:
        entry = db.query(TTSEngineEndpoint).filter(
            TTSEngineEndpoint.engine_id == engine_id
        ).first()
        if entry:
            return RemoteTTSClient(entry.base_url, entry.api_key)
        return None
    finally:
        db.close()


def get_library_voice_path(voice_id: str) -> str:
    """Get file path for a library voice.
    Checks filesystem first, then falls back to VoiceLibraryEntry DB table."""
    import tempfile
    
    voice_samples_dir = os.path.join(os.path.dirname(__file__), "..", "voice_samples")
    mic1_path = os.path.join(voice_samples_dir, f"{voice_id}_mic1.wav")
    mic2_path = os.path.join(voice_samples_dir, f"{voice_id}_mic2.wav")
    
    if os.path.exists(mic1_path):
        return mic1_path
    if os.path.exists(mic2_path):
        return mic2_path
    
    db = get_db_session()
    try:
        entry = db.query(VoiceLibraryEntry).filter(VoiceLibraryEntry.id == voice_id).first()
        if entry and entry.audio_data:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(entry.audio_data)
            tmp.flush()
            tmp.close()
            return tmp.name
    finally:
        db.close()
    
    raise FileNotFoundError(f"Voice file not found: {voice_id}")


def get_uploaded_voice_path(voice_id: str) -> str:
    """Get file path for an uploaded voice sample.
    Checks filesystem uploads first, then falls back to CustomVoice DB table."""
    import tempfile
    uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
    for ext in ['.wav', '.mp3', '.ogg', '.flac']:
        path = os.path.join(uploads_dir, f"{voice_id}{ext}")
        if os.path.exists(path):
            return path
    
    db = get_db_session()
    try:
        custom_voice = db.query(CustomVoice).filter(CustomVoice.id == voice_id).first()
        if custom_voice:
            tmp = tempfile.NamedTemporaryFile(
                suffix=custom_voice.file_ext or ".wav", delete=False
            )
            tmp.write(custom_voice.audio_data)
            tmp.flush()
            tmp.close()
            return tmp.name
    finally:
        db.close()
    
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


def _launch_job_thread(job_id: str, engine: str):
    cancel_token = threading.Event()
    _cancel_tokens[job_id] = cancel_token

    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process_job(job_id, cancel_token))
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            update_job_status(job_id, JobStatus.FAILED, error_message=str(e))
            if job_id in active_jobs:
                del active_jobs[job_id]
        finally:
            loop.close()
            _cancel_tokens.pop(job_id, None)
            _start_next_for_engine(engine)

    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    active_jobs[job_id] = thread
    logger.info(f"Started job {job_id} for engine '{engine}' in background thread")


def start_job_async(job_id: str):
    """Start processing a job, or queue it if the engine is busy."""
    db = get_db_session()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if not job:
            logger.error(f"start_job_async: job {job_id} not found")
            return
        engine = job.tts_engine or "edge-tts"
    finally:
        db.close()

    with _engine_guard:
        if not _engine_busy.get(engine, False):
            _engine_busy[engine] = True
            logger.info(f"Engine '{engine}' is free — starting job {job_id} immediately")
            _launch_job_thread(job_id, engine)
        else:
            logger.info(f"Engine '{engine}' is busy — job {job_id} queued as waiting")
            update_job_status(job_id, JobStatus.WAITING, error_message=f"Waiting — engine '{engine}' is busy with another job")
            _engine_queues[engine].append(job_id)


def remove_job_from_engine_queue(job_id: str, engine: str = None):
    """Remove a waiting job from the engine queue (used for cancellation)."""
    with _engine_guard:
        if engine:
            queue = _engine_queues.get(engine, [])
            if job_id in queue:
                queue.remove(job_id)
        else:
            for q in _engine_queues.values():
                if job_id in q:
                    q.remove(job_id)
                    break
