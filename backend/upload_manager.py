"""
Upload Manager - Handles file uploads and background analysis jobs.
"""
import json
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

from database import (
    FileUpload, FileChapter, UploadStatus,
    get_db_session
)
from epub_parser import parse_epub, parse_txt
from text_parser import TextParser

import logging
logger = logging.getLogger(__name__)


class UploadManager:
    """Manages file uploads and their analysis."""
    
    def __init__(self):
        self.parser = TextParser()
        self._analysis_threads: Dict[str, threading.Thread] = {}
    
    def create_upload(
        self,
        filename: str,
        file_content: bytes,
        tts_engine: str = "edge-tts"
    ) -> FileUpload:
        """
        Create a new file upload and extract chapters.
        
        Args:
            filename: Original filename
            file_content: Raw file bytes
            tts_engine: TTS engine to use for generation
            
        Returns:
            Created FileUpload object
        """
        filetype = "epub" if filename.lower().endswith(".epub") else "txt"
        
        if filetype == "epub":
            chapters = parse_epub(file_content)
        else:
            chapters = parse_txt(file_content)
        
        db = get_db_session()
        try:
            upload = FileUpload(
                filename=filename,
                filetype=filetype,
                tts_engine=tts_engine,
                total_chapters=len(chapters),
                status=UploadStatus.PENDING.value
            )
            db.add(upload)
            db.flush()
            
            for idx, (title, text) in enumerate(chapters):
                chapter = FileChapter(
                    upload_id=upload.id,
                    chapter_index=idx,
                    title=title,
                    raw_text=text,
                    status=UploadStatus.PENDING.value
                )
                db.add(chapter)
            
            db.commit()
            db.refresh(upload)
            
            logger.info(f"Created upload {upload.id} with {len(chapters)} chapters")
            return upload
            
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def start_analysis(self, upload_id: str):
        """
        Start background analysis for an upload.
        
        Args:
            upload_id: ID of the upload to analyze
        """
        if upload_id in self._analysis_threads:
            existing = self._analysis_threads[upload_id]
            if existing.is_alive():
                logger.warning(f"Analysis already running for upload {upload_id}")
                return
        
        thread = threading.Thread(
            target=self._run_analysis,
            args=(upload_id,),
            daemon=True
        )
        self._analysis_threads[upload_id] = thread
        thread.start()
        
        logger.info(f"Started analysis thread for upload {upload_id}")
    
    def _run_analysis(self, upload_id: str):
        """Background thread for analyzing chapters."""
        db = get_db_session()
        try:
            upload = db.query(FileUpload).filter(FileUpload.id == upload_id).first()
            if not upload:
                logger.error(f"Upload {upload_id} not found")
                return
            
            upload.status = UploadStatus.ANALYZING.value
            upload.updated_at = datetime.utcnow()
            db.commit()
            
            chapters = db.query(FileChapter).filter(
                FileChapter.upload_id == upload_id
            ).order_by(FileChapter.chapter_index).all()
            
            all_speakers = set()
            
            for chapter in chapters:
                try:
                    chapter.status = UploadStatus.ANALYZING.value
                    chapter.updated_at = datetime.utcnow()
                    db.commit()
                    
                    raw_text = str(chapter.raw_text) if chapter.raw_text else ""
                    parsed_segments, detected_speakers = self.parser.parse(raw_text)
                    
                    segments = [
                        {
                            "id": s.id,
                            "text": s.text,
                            "type": s.type,
                            "speaker": s.speaker,
                            "sentiment": {
                                "label": s.sentiment.label if s.sentiment else "neutral",
                                "score": s.sentiment.score if s.sentiment else 0.5
                            }
                        }
                        for s in parsed_segments
                    ]
                    
                    speakers = detected_speakers
                    all_speakers.update(speakers)
                    
                    chapter.analysis_json = json.dumps({
                        "segments": segments,
                        "speakers": list(speakers)
                    })
                    chapter.status = UploadStatus.ANALYZED.value
                    chapter.updated_at = datetime.utcnow()
                    db.commit()
                    
                    logger.info(f"Analyzed chapter {chapter.chapter_index}: {len(segments)} segments")
                    
                except Exception as e:
                    logger.error(f"Failed to analyze chapter {chapter.chapter_index}: {e}")
                    chapter.status = UploadStatus.FAILED.value
                    chapter.error_message = str(e)
                    chapter.updated_at = datetime.utcnow()
                    db.commit()
            
            failed_chapters = db.query(FileChapter).filter(
                FileChapter.upload_id == upload_id,
                FileChapter.status == UploadStatus.FAILED.value
            ).count()
            
            if failed_chapters == len(chapters):
                upload.status = UploadStatus.FAILED.value
                upload.error_message = "All chapters failed to analyze"
            else:
                upload.status = UploadStatus.ANALYZED.value
            
            upload.updated_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Analysis complete for upload {upload_id}: {len(all_speakers)} speakers detected")
            
        except Exception as e:
            logger.error(f"Analysis failed for upload {upload_id}: {e}")
            try:
                upload = db.query(FileUpload).filter(FileUpload.id == upload_id).first()
                if upload:
                    upload.status = UploadStatus.FAILED.value
                    upload.error_message = str(e)
                    upload.updated_at = datetime.utcnow()
                    db.commit()
            except:
                pass
        finally:
            db.close()
            if upload_id in self._analysis_threads:
                del self._analysis_threads[upload_id]
    
    def get_upload(self, upload_id: str) -> Optional[Dict[str, Any]]:
        """Get upload with its chapters and analysis status."""
        db = get_db_session()
        try:
            upload = db.query(FileUpload).filter(FileUpload.id == upload_id).first()
            if not upload:
                return None
            
            chapters = db.query(FileChapter).filter(
                FileChapter.upload_id == upload_id
            ).order_by(FileChapter.chapter_index).all()
            
            analyzed_count = sum(1 for c in chapters if c.status == UploadStatus.ANALYZED.value)
            
            all_speakers = set()
            for chapter in chapters:
                if chapter.analysis_json:
                    try:
                        data = json.loads(chapter.analysis_json)
                        all_speakers.update(data.get('speakers', []))
                    except:
                        pass
            
            return {
                "id": upload.id,
                "filename": upload.filename,
                "filetype": upload.filetype,
                "status": upload.status,
                "ttsEngine": upload.tts_engine,
                "totalChapters": upload.total_chapters,
                "analyzedChapters": analyzed_count,
                "errorMessage": upload.error_message,
                "createdAt": upload.created_at.isoformat(),
                "chapters": [
                    {
                        "id": c.id,
                        "index": c.chapter_index,
                        "title": c.title,
                        "status": c.status,
                        "ttsJobId": c.tts_job_id,
                        "hasAnalysis": c.analysis_json is not None,
                        "errorMessage": c.error_message
                    }
                    for c in chapters
                ],
                "detectedSpeakers": list(all_speakers)
            }
        finally:
            db.close()
    
    def get_chapter_analysis(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        """Get analysis results for a specific chapter."""
        db = get_db_session()
        try:
            chapter = db.query(FileChapter).filter(FileChapter.id == chapter_id).first()
            if not chapter or not chapter.analysis_json:
                return None
            
            return json.loads(chapter.analysis_json)
        finally:
            db.close()
    
    def list_uploads(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent uploads."""
        db = get_db_session()
        try:
            uploads = db.query(FileUpload).order_by(
                FileUpload.created_at.desc()
            ).limit(limit).all()
            
            result = []
            for upload in uploads:
                chapters = db.query(FileChapter).filter(
                    FileChapter.upload_id == upload.id
                ).all()
                analyzed_count = sum(1 for c in chapters if c.status == UploadStatus.ANALYZED.value)
                
                result.append({
                    "id": upload.id,
                    "filename": upload.filename,
                    "filetype": upload.filetype,
                    "status": upload.status,
                    "ttsEngine": upload.tts_engine,
                    "totalChapters": upload.total_chapters,
                    "analyzedChapters": analyzed_count,
                    "createdAt": upload.created_at.isoformat()
                })
            
            return result
        finally:
            db.close()
    
    def delete_upload(self, upload_id: str) -> bool:
        """Delete an upload and all its chapters."""
        db = get_db_session()
        try:
            upload = db.query(FileUpload).filter(FileUpload.id == upload_id).first()
            if not upload:
                return False
            
            db.delete(upload)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete upload {upload_id}: {e}")
            return False
        finally:
            db.close()


upload_manager = UploadManager()
