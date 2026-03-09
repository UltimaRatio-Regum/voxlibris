"""
Database configuration and models for TTS job persistence.
Uses SQLAlchemy with asyncpg for async PostgreSQL operations.
"""
import os
import uuid
from datetime import datetime
from typing import Optional, List
from enum import Enum

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, ForeignKey, 
    Enum as SQLEnum, LargeBinary, Boolean, JSON, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.environ.get("DATABASE_URL", "")

Base = declarative_base()


class JobStatus(str, Enum):
    PENDING = "pending"
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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    chapters = relationship("FileChapter", back_populates="upload", cascade="all, delete-orphan")


class FileChapter(Base):
    """Represents a chapter within an uploaded file."""
    __tablename__ = "file_chapters"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id = Column(String, ForeignKey("file_uploads.id", ondelete="CASCADE"), nullable=False)
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
    status = Column(String, nullable=False, default=JobStatus.PENDING.value)
    total_segments = Column(Integer, nullable=False, default=0)
    completed_segments = Column(Integer, nullable=False, default=0)
    failed_segments = Column(Integer, nullable=False, default=0)
    tts_engine = Column(String, nullable=False, default="edge-tts")
    narrator_voice_id = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    config_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    segments = relationship("TTSSegment", back_populates="job", cascade="all, delete-orphan")


class TTSSegment(Base):
    """Represents a single segment within a TTS job."""
    __tablename__ = "tts_segments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("tts_jobs.id", ondelete="CASCADE"), nullable=False)
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
    supported_emotions_json = Column(Text, nullable=True)
    extra_properties_json = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
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
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class CustomVoice(Base):
    """User-uploaded custom voice sample, stored as a blob in the database."""
    __tablename__ = "custom_voices"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    audio_data = Column(LargeBinary, nullable=False)
    file_ext = Column(String, nullable=False, default=".wav")
    duration = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


engine = None
SessionLocal = None


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
