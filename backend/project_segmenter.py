import uuid
import json
import logging
import threading
from typing import Optional

from database import (
    get_db_session, Project, ProjectChapter, ProjectSection, ProjectChunk
)
from text_parser import TextParser

logger = logging.getLogger(__name__)

SECTION_WORD_LIMIT = 300
WORDS_PER_SECOND = 2.5

text_parser = TextParser()


def split_into_sections(raw_text: str, word_limit: int = SECTION_WORD_LIMIT) -> list[str]:
    paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]
    if not paragraphs:
        return [raw_text] if raw_text.strip() else []

    sections: list[str] = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_words + para_words > word_limit and current:
            sections.append("\n\n".join(current))
            current = [para]
            current_words = para_words
        else:
            current.append(para)
            current_words += para_words

    if current:
        sections.append("\n\n".join(current))

    return sections


def segment_project_background(project_id: str, use_llm: bool = False):
    thread = threading.Thread(
        target=_run_segmentation,
        args=(project_id, use_llm),
        daemon=True
    )
    thread.start()
    return thread


def _run_segmentation(project_id: str, use_llm: bool = False):
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            logger.error(f"Project {project_id} not found")
            return

        project.status = "segmenting"
        db.commit()

        chapters = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).order_by(ProjectChapter.chapter_index).all()

        all_known_speakers: list[str] = []

        for chapter in chapters:
            try:
                chapter.status = "segmenting"
                db.commit()

                section_texts = split_into_sections(chapter.raw_text)
                chunk_global_index = 0

                for sec_idx, section_text in enumerate(section_texts):
                    section = ProjectSection(
                        id=str(uuid.uuid4()),
                        chapter_id=chapter.id,
                        section_index=sec_idx,
                        status="processing",
                    )
                    db.add(section)
                    db.commit()

                    try:
                        segments, detected_speakers = text_parser.parse(
                            section_text, known_speakers=all_known_speakers
                        )
                        for sp in detected_speakers:
                            if sp and sp not in all_known_speakers:
                                all_known_speakers.append(sp)

                        for seg_idx, seg in enumerate(segments):
                            if hasattr(seg, 'dict'):
                                seg_dict = seg.dict() if hasattr(seg, 'dict') else seg
                            else:
                                seg_dict = seg

                            seg_text = seg_dict.get("text", "") if isinstance(seg_dict, dict) else getattr(seg, "text", "")
                            seg_type = seg_dict.get("type", "narration") if isinstance(seg_dict, dict) else getattr(seg, "type", "narration")
                            seg_speaker = seg_dict.get("speaker") if isinstance(seg_dict, dict) else getattr(seg, "speaker", None)
                            seg_sentiment = seg_dict.get("sentiment") if isinstance(seg_dict, dict) else getattr(seg, "sentiment", None)
                            seg_wc = seg_dict.get("wordCount") if isinstance(seg_dict, dict) else getattr(seg, "wordCount", None)

                            wc = seg_wc or len(seg_text.split())
                            emotion = "neutral"
                            if seg_sentiment:
                                if isinstance(seg_sentiment, dict):
                                    emotion = seg_sentiment.get("label", "neutral")
                                elif hasattr(seg_sentiment, "label"):
                                    emotion = seg_sentiment.label

                            chunk = ProjectChunk(
                                id=str(uuid.uuid4()),
                                section_id=section.id,
                                chunk_index=chunk_global_index,
                                text=seg_text,
                                segment_type=seg_type,
                                speaker=seg_speaker,
                                emotion=emotion,
                                word_count=wc,
                                approx_duration_seconds=round(wc / WORDS_PER_SECOND, 1),
                            )
                            db.add(chunk)
                            chunk_global_index += 1

                        section.status = "segmented"
                        db.commit()

                    except Exception as e:
                        logger.error(f"Failed to segment section {sec_idx} of chapter {chapter.chapter_index}: {e}")
                        section.status = "failed"
                        section.error_message = str(e)
                        db.commit()

                if all_known_speakers:
                    chapter.speakers_json = json.dumps(all_known_speakers)

                chapter.status = "segmented"
                db.commit()

            except Exception as e:
                logger.error(f"Failed to segment chapter {chapter.chapter_index}: {e}")
                chapter.status = "failed"
                chapter.error_message = str(e)
                db.commit()

        failed_chapters = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project_id,
            ProjectChapter.status == "failed"
        ).count()

        if failed_chapters == len(chapters):
            project.status = "failed"
            project.error_message = "All chapters failed to segment"
        else:
            project.status = "segmented"

        if all_known_speakers:
            project.speakers_json = json.dumps(
                {sp: {"name": sp, "voiceSampleId": None, "pitchOffset": 0, "speedFactor": 1.0}
                 for sp in all_known_speakers}
            )

        db.commit()
        logger.info(f"Project {project_id} segmentation complete: {project.status}")

    except Exception as e:
        logger.error(f"Project segmentation failed: {e}")
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.status = "failed"
                project.error_message = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
