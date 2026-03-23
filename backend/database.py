"""
Database configuration and models for TTS job persistence.
Uses SQLAlchemy with asyncpg for async PostgreSQL operations.
"""
import os
import uuid
import logging
from datetime import datetime
from typing import Optional, List
from enum import Enum

import bcrypt
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, ForeignKey, 
    Enum as SQLEnum, LargeBinary, Boolean, JSON, Index, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    user_type = Column(String, nullable=False, default="user")
    is_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class InvitationCode(Base):
    __tablename__ = "invitation_codes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String, nullable=False, unique=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    used_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    used_at = Column(DateTime, nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class JobStatus(str, Enum):
    PENDING = "pending"
    WAITING = "waiting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SegmentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    FAILED = "failed"


class FileUpload(Base):
    """Represents an uploaded file (txt or epub) for processing."""
    __tablename__ = "file_uploads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    filetype = Column(String, nullable=False)  # "txt" or "epub"
    status = Column(String, nullable=False, default=UploadStatus.PENDING.value)
    tts_engine = Column(String, nullable=False, default="edge-tts")
    total_chapters = Column(Integer, nullable=False, default=1)
    error_message = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    chapters = relationship("FileChapter", back_populates="upload", cascade="all, delete-orphan")


class FileChapter(Base):
    """Represents a chapter within an uploaded file."""
    __tablename__ = "file_chapters"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String, ForeignKey("file_uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_index = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default=UploadStatus.PENDING.value)
    analysis_json = Column(Text, nullable=True)  # JSON: {segments: [], speakers: []}
    tts_job_id = Column(String, nullable=True)  # Reference to TTS job when generated
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    upload = relationship("FileUpload", back_populates="chapters")


class TTSJob(Base):
    """Represents a TTS generation job that processes multiple segments."""
    __tablename__ = "tts_jobs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False, default="Untitled")
    status = Column(String, nullable=False, default=JobStatus.PENDING.value, index=True)
    total_segments = Column(Integer, nullable=False, default=0)
    completed_segments = Column(Integer, nullable=False, default=0)
    failed_segments = Column(Integer, nullable=False, default=0)
    tts_engine = Column(String, nullable=False, default="edge-tts")
    narrator_voice_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    config_json = Column(Text, nullable=True)
    job_group_id = Column(String, nullable=True)
    job_type = Column(String, nullable=False, default="tts")
    project_id = Column(String, nullable=True)
    export_format = Column(String, nullable=True)
    output_audio_file_id = Column(String, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    segments = relationship("TTSSegment", back_populates="job", cascade="all, delete-orphan")


class TTSSegment(Base):
    """Represents a single segment within a TTS job."""
    __tablename__ = "tts_segments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("tts_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    segment_type = Column(String, nullable=False, default="narration")
    speaker = Column(String, nullable=True)
    sentiment = Column(String, nullable=True)
    status = Column(String, nullable=False, default=SegmentStatus.PENDING.value)
    audio_path = Column(String, nullable=True)
    audio_data = Column(LargeBinary, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    job = relationship("TTSJob", back_populates="segments")


class TTSEngineEndpoint(Base):
    """Registered external TTS engine with its cached details."""
    __tablename__ = "tts_engine_endpoints"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    engine_id = Column(String, nullable=False, unique=True)
    engine_name = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    api_key = Column(String, nullable=True)
    sample_rate = Column(Integer, nullable=False, default=24000)
    bit_depth = Column(Integer, nullable=False, default=16)
    channels = Column(Integer, nullable=False, default=1)
    max_seconds_per_conversion = Column(Integer, nullable=False, default=30)
    supports_voice_cloning = Column(Boolean, nullable=False, default=False)
    builtin_voices_json = Column(Text, nullable=True)
    base_voices_json = Column(Text, nullable=True)
    supported_emotions_json = Column(Text, nullable=True)
    extra_properties_json = Column(Text, nullable=True)
    engine_params_json = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    is_shared = Column(Boolean, nullable=False, default=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    last_test_success = Column(Boolean, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class VoiceLibraryEntry(Base):
    """Voice sample stored in the database for voice cloning."""
    __tablename__ = "voice_library"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    gender = Column(String, nullable=False)
    age = Column(Integer, nullable=True)
    language = Column(String, nullable=True)
    location = Column(String, nullable=True)
    transcript = Column(Text, nullable=True)
    duration = Column(Float, nullable=False, default=0.0)
    audio_data = Column(LargeBinary, nullable=False)
    alt_audio_data = Column(LargeBinary, nullable=True)
    is_shared = Column(Boolean, nullable=False, default=True)
    audio_hash = Column(String(64), nullable=True, index=True)
    metadata_json = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CustomVoice(Base):
    """User-uploaded custom voice sample, stored as a blob in the database."""
    __tablename__ = "custom_voices"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    audio_data = Column(LargeBinary, nullable=False)
    file_ext = Column(String, nullable=False, default=".wav")
    duration = Column(Float, nullable=False, default=0.0)
    gender = Column(String, nullable=True)
    language = Column(String, nullable=True)
    transcript = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    SEGMENTING = "segmenting"
    SEGMENTED = "segmented"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default=ProjectStatus.DRAFT.value)
    tts_engine = Column(String, nullable=False, default="edge-tts")
    narrator_voice_id = Column(String, nullable=True)
    narrator_speed = Column(Float, nullable=False, default=1.0)
    base_voice_id = Column(String, nullable=True)
    exaggeration = Column(Float, nullable=False, default=0.5)
    pause_duration = Column(Float, nullable=False, default=150.0)
    speakers_json = Column(Text, nullable=True)
    narrator_emotion = Column(String, nullable=False, default="auto")
    dialogue_emotion_mode = Column(String, nullable=False, default="per-chunk")
    source_type = Column(String, nullable=False, default="text")
    source_filename = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    output_format = Column(String, nullable=False, default="mp3")
    meta_author = Column(String, nullable=True)
    meta_narrator = Column(String, nullable=True)
    meta_genre = Column(String, nullable=True)
    meta_year = Column(String, nullable=True)
    meta_description = Column(Text, nullable=True)
    engine_options_json = Column(Text, nullable=True)
    meta_cover_image = Column(LargeBinary, nullable=True)
    source_file_data = Column(LargeBinary, nullable=True)
    source_file_ext = Column(String, nullable=True)
    segmentation_started_at = Column(DateTime, nullable=True)
    total_text_length = Column(Integer, nullable=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    chapters = relationship("ProjectChapter", back_populates="project", cascade="all, delete-orphan", order_by="ProjectChapter.chapter_index")


class ProjectChapter(Base):
    __tablename__ = "project_chapters"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_index = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    raw_text = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")
    speakers_json = Column(Text, nullable=True)
    tts_engine = Column(String, nullable=True)
    narrator_voice_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="chapters")
    sections = relationship("ProjectSection", back_populates="chapter", cascade="all, delete-orphan", order_by="ProjectSection.section_index")


class ProjectSection(Base):
    __tablename__ = "project_sections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chapter_id = Column(String, ForeignKey("project_chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    section_index = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    raw_text = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    chapter = relationship("ProjectChapter", back_populates="sections")
    chunks = relationship("ProjectChunk", back_populates="section", cascade="all, delete-orphan", order_by="ProjectChunk.chunk_index")


class ProjectChunk(Base):
    __tablename__ = "project_chunks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    section_id = Column(String, ForeignKey("project_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    segment_type = Column(String, nullable=False, default="narration")
    speaker = Column(String, nullable=True)
    emotion = Column(String, nullable=False, default="neutral")
    speaker_override = Column(String, nullable=True)
    emotion_override = Column(String, nullable=True)
    word_count = Column(Integer, nullable=False, default=0)
    approx_duration_seconds = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    section = relationship("ProjectSection", back_populates="chunks")


class ProjectAudioFile(Base):
    __tablename__ = "project_audio_files"
    __table_args__ = (
        Index("ix_project_audio_scope", "project_id", "scope_type", "scope_id"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_type = Column(String, nullable=False)
    scope_id = Column(String, nullable=False)
    audio_data = Column(LargeBinary, nullable=True)
    file_path = Column(String, nullable=True)
    format = Column(String, nullable=False, default="mp3")
    duration_seconds = Column(Float, nullable=True)
    tts_engine = Column(String, nullable=True)
    voice_id = Column(String, nullable=True)
    settings_json = Column(Text, nullable=True)
    label = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ProjectValidationConfig(Base):
    """Per-project configuration for the audio validation pipeline."""
    __tablename__ = "project_validation_configs"

    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    stt_model = Column(String, nullable=False, default="google/gemini-2.5-flash")
    algorithms = Column(Text, nullable=False, default='["sequence_matcher","levenshtein","token_sort"]')
    combination_method = Column(String, nullable=False, default="average")  # average | max | min
    drop_worst_n = Column(Integer, nullable=False, default=0)
    similarity_cutoff = Column(Float, nullable=False, default=0.80)
    auto_regenerate = Column(Boolean, nullable=False, default=False)
    use_phonetic = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChunkValidationResult(Base):
    """STT result and similarity scores for a single chunk in a validation run."""
    __tablename__ = "chunk_validation_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String, ForeignKey("project_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(String, ForeignKey("tts_jobs.id", ondelete="SET NULL"), nullable=True)
    stt_text = Column(Text, nullable=True)
    processed_source_text = Column(Text, nullable=True)  # normalized/phonetic text used for comparison
    processed_stt_text = Column(Text, nullable=True)     # normalized/phonetic text used for comparison
    algorithm_scores = Column(Text, nullable=True)  # JSON: {"sequence_matcher": 0.91, ...}
    combined_score = Column(Float, nullable=True)
    is_flagged = Column(Boolean, nullable=False, default=False)
    is_regenerated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ValidationHistory(Base):
    """Permanent log of every per-chunk validation result across all runs.
    Intended as a training dataset for future ML-based quality prediction."""
    __tablename__ = "validation_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(String, ForeignKey("project_chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    validation_job_id = Column(String, ForeignKey("tts_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    # Raw texts
    source_text = Column(Text, nullable=True)
    stt_text = Column(Text, nullable=True)
    # Derived length features (useful regression inputs)
    source_char_length = Column(Integer, nullable=True)
    stt_char_length = Column(Integer, nullable=True)
    source_word_count = Column(Integer, nullable=True)
    stt_word_count = Column(Integer, nullable=True)
    # Validation config used for this run
    use_phonetic = Column(Boolean, nullable=False, default=False)
    combined_score = Column(Float, nullable=True)
    combination_method = Column(String, nullable=True)
    drop_worst_n = Column(Integer, nullable=True)
    similarity_cutoff = Column(Float, nullable=True)
    # Outcome labels
    is_flagged = Column(Boolean, nullable=False, default=False)
    is_good = Column(Boolean, nullable=False, default=False)       # manually marked as good
    is_regenerated = Column(Boolean, nullable=False, default=False)
    regen_type = Column(String, nullable=True)                     # null | "manual" | "batch" | "auto"
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    scores = relationship("ValidationAlgorithmScore", back_populates="history", cascade="all, delete-orphan")


class ValidationAlgorithmScore(Base):
    """Raw per-algorithm similarity score for a single chunk in a validation run."""
    __tablename__ = "validation_algorithm_scores"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    history_id = Column(String, ForeignKey("validation_history.id", ondelete="CASCADE"), nullable=False, index=True)
    algorithm = Column(String, nullable=False)
    score = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    history = relationship("ValidationHistory", back_populates="scores")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


engine = None
SessionLocal = None


def _migrate_columns(db_engine):
    """Add missing columns to existing tables for backward compatibility."""
    from sqlalchemy import text, inspect
    
    inspector = inspect(db_engine)
    
    migrations = [
        ("projects", "user_id", "ALTER TABLE projects ADD COLUMN user_id VARCHAR REFERENCES users(id)"),
        ("custom_voices", "user_id", "ALTER TABLE custom_voices ADD COLUMN user_id VARCHAR REFERENCES users(id)"),
        ("tts_engine_endpoints", "user_id", "ALTER TABLE tts_engine_endpoints ADD COLUMN user_id VARCHAR REFERENCES users(id)"),
        ("tts_engine_endpoints", "is_shared", "ALTER TABLE tts_engine_endpoints ADD COLUMN is_shared BOOLEAN NOT NULL DEFAULT true"),
        ("voice_library", "user_id", "ALTER TABLE voice_library ADD COLUMN user_id VARCHAR REFERENCES users(id)"),
        ("voice_library", "is_shared", "ALTER TABLE voice_library ADD COLUMN is_shared BOOLEAN NOT NULL DEFAULT true"),
        ("tts_jobs", "user_id", "ALTER TABLE tts_jobs ADD COLUMN user_id VARCHAR REFERENCES users(id)"),
        ("projects", "narrator_speed", "ALTER TABLE projects ADD COLUMN narrator_speed FLOAT NOT NULL DEFAULT 1.0"),
        ("project_sections", "raw_text", "ALTER TABLE project_sections ADD COLUMN raw_text TEXT"),
        ("file_uploads", "user_id", "ALTER TABLE file_uploads ADD COLUMN user_id VARCHAR REFERENCES users(id)"),
        ("tts_jobs", "job_type", "ALTER TABLE tts_jobs ADD COLUMN job_type VARCHAR NOT NULL DEFAULT 'tts'"),
        ("tts_jobs", "project_id", "ALTER TABLE tts_jobs ADD COLUMN project_id VARCHAR"),
        ("tts_jobs", "export_format", "ALTER TABLE tts_jobs ADD COLUMN export_format VARCHAR"),
        ("tts_jobs", "output_audio_file_id", "ALTER TABLE tts_jobs ADD COLUMN output_audio_file_id VARCHAR"),
        ("projects", "source_file_data", "ALTER TABLE projects ADD COLUMN source_file_data BYTEA"),
        ("projects", "source_file_ext", "ALTER TABLE projects ADD COLUMN source_file_ext VARCHAR"),
        ("projects", "segmentation_started_at", "ALTER TABLE projects ADD COLUMN segmentation_started_at TIMESTAMP"),
        ("projects", "total_text_length", "ALTER TABLE projects ADD COLUMN total_text_length INTEGER"),
        ("project_audio_files", "audio_data_nullable", "ALTER TABLE project_audio_files ALTER COLUMN audio_data DROP NOT NULL"),
        ("project_audio_files", "file_path", "ALTER TABLE project_audio_files ADD COLUMN file_path VARCHAR"),
        ("tts_engine_endpoints", "engine_params_json", "ALTER TABLE tts_engine_endpoints ADD COLUMN engine_params_json TEXT"),
        ("projects", "engine_options_json", "ALTER TABLE projects ADD COLUMN engine_options_json TEXT"),
        ("voice_library", "metadata_json", "ALTER TABLE voice_library ADD COLUMN metadata_json TEXT"),
        ("custom_voices", "gender", "ALTER TABLE custom_voices ADD COLUMN gender VARCHAR"),
        ("custom_voices", "language", "ALTER TABLE custom_voices ADD COLUMN language VARCHAR"),
        ("custom_voices", "transcript", "ALTER TABLE custom_voices ADD COLUMN transcript TEXT"),
        ("custom_voices", "metadata_json", "ALTER TABLE custom_voices ADD COLUMN metadata_json TEXT"),
        ("voice_library", "audio_hash", "ALTER TABLE voice_library ADD COLUMN audio_hash VARCHAR(64)"),
        ("project_validation_configs", "use_phonetic", "ALTER TABLE project_validation_configs ADD COLUMN use_phonetic BOOLEAN NOT NULL DEFAULT false"),
        ("chunk_validation_results", "processed_source_text", "ALTER TABLE chunk_validation_results ADD COLUMN processed_source_text TEXT"),
        ("chunk_validation_results", "processed_stt_text", "ALTER TABLE chunk_validation_results ADD COLUMN processed_stt_text TEXT"),
    ]
    
    with db_engine.connect() as conn:
        for table_name, column_name, sql in migrations:
            try:
                columns = [c["name"] for c in inspector.get_columns(table_name)]
                if column_name not in columns:
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Added column {column_name} to {table_name}")
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.debug(f"Migration skipped for {table_name}.{column_name}: {e}")

    _create_indexes(db_engine, inspector)


def _create_indexes(db_engine, inspector):
    """Create indexes on FK columns for existing databases."""
    from sqlalchemy import text

    index_defs = [
        ("ix_tts_segments_job_id", "tts_segments", "job_id"),
        ("ix_tts_jobs_status", "tts_jobs", "status"),
        ("ix_file_chapters_upload_id", "file_chapters", "upload_id"),
        ("ix_project_chapters_project_id", "project_chapters", "project_id"),
        ("ix_project_sections_chapter_id", "project_sections", "chapter_id"),
        ("ix_project_chunks_section_id", "project_chunks", "section_id"),
        ("ix_project_audio_files_project_id", "project_audio_files", "project_id"),
        ("ix_project_audio_scope", "project_audio_files", "project_id, scope_type, scope_id"),
    ]

    with db_engine.connect() as conn:
        existing_tables = inspector.get_table_names()
        for idx_name, table_name, columns in index_defs:
            if table_name not in existing_tables:
                continue
            existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name) if idx.get("name")}
            if idx_name in existing_indexes:
                continue
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({columns})"))
                conn.commit()
                logger.info(f"Created index {idx_name} on {table_name}({columns})")
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                logger.debug(f"Index creation skipped for {idx_name}: {e}")


def _assign_orphaned_records(session):
    """Assign records with NULL user_id to the seed admin account."""
    try:
        admin = session.query(User).filter(User.user_type == "administrator").first()
        if not admin:
            return
        admin_id = admin.id
        
        updated = 0
        for model in [Project, CustomVoice, TTSEngineEndpoint, TTSJob, FileUpload]:
            count = session.query(model).filter(model.user_id == None).update(
                {model.user_id: admin_id}, synchronize_session=False
            )
            updated += count
        
        if updated > 0:
            session.commit()
            logger.info(f"Assigned {updated} orphaned records to admin user {admin_id}")
    except Exception as e:
        session.rollback()
        logger.warning(f"Could not assign orphaned records: {e}")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _seed_admin(session):
    existing = session.query(User).first()
    if existing is None:
        admin = User(
            id=str(uuid.uuid4()),
            username="Administrator",
            email="admin@localhost",
            password_hash=_hash_password("ChangeMe"),
            display_name="Administrator",
            user_type="administrator",
            is_enabled=True,
        )
        session.add(admin)

        reg_setting = session.query(SystemSetting).filter(SystemSetting.key == "registration_mode").first()
        if reg_setting is None:
            session.add(SystemSetting(key="registration_mode", value="disabled"))

        session.commit()
        logger.info("Seeded administrator account (username: Administrator, password: ChangeMe)")


def init_database():
    """Initialize the database connection and create tables."""
    global engine, SessionLocal
    
    if not DATABASE_URL:
        print("WARNING: DATABASE_URL not set, using in-memory SQLite")
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
    else:
        engine = create_engine(DATABASE_URL)
    
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    _migrate_columns(engine)

    try:
        session = SessionLocal()
        try:
            _seed_admin(session)
            _assign_orphaned_records(session)
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Could not seed admin account: {e}")

    return engine


def get_db():
    """Get a database session."""
    if SessionLocal is None:
        init_database()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Get a database session directly (not as generator)."""
    if SessionLocal is None:
        init_database()
    return SessionLocal()
