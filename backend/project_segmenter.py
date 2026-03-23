import uuid
import re
import json
import logging
import os
import asyncio
import threading
from datetime import datetime
from typing import Optional, List
import httpx

from database import (
    get_db_session, Project, ProjectChapter, ProjectSection, ProjectChunk,
    AppSetting,
)

logger = logging.getLogger(__name__)

# In-memory progress for the chapter currently being segmented.
# Keyed by project_id.  Reset to 0 at the start of each chapter so completed
# chapters (whose chunks are already in the DB) are not double-counted.
_chapter_chars_in_progress: dict[str, int] = {}


def get_chapter_chars_in_progress(project_id: str) -> int:
    return _chapter_chars_in_progress.get(project_id, 0)


SECTION_WORD_LIMIT = 300
MAX_CHUNKS_PER_SECTION = 30
WORDS_PER_SECOND = 2.5

DEFAULT_MODEL = "openai/gpt-4.1-mini"

CANONICAL_EMOTIONS = [
    "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
    "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
]

PARSING_PROMPT_SETTING_KEY = "parsing_prompt"


def _load_prompt() -> Optional[str]:
    db = get_db_session()
    try:
        setting = db.query(AppSetting).filter(AppSetting.key == PARSING_PROMPT_SETTING_KEY).first()
        if setting and setting.value:
            return setting.value
        return None
    except Exception as e:
        logger.warning(f"Failed to load parsing prompt from database: {e}")
        return None
    finally:
        db.close()


def split_into_sections(raw_text: str, word_limit: int = SECTION_WORD_LIMIT) -> list[str]:
    paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]

    if len(paragraphs) <= 1:
        single_newline = [p.strip() for p in raw_text.split("\n") if p.strip()]
        if len(single_newline) > 1:
            paragraphs = single_newline

    if len(paragraphs) <= 1 and raw_text.strip():
        sentences = re.split(r'(?<=[.!?])\s+', raw_text.strip())
        if len(sentences) > 1:
            paragraphs = sentences

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


def _rechunk_segment(text: str, max_words: int = 40) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]

    chunks = []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    current = []
    current_wc = 0
    for sent in sentences:
        swc = len(sent.split())
        if current_wc + swc > max_words and current:
            chunks.append(" ".join(current))
            current = [sent]
            current_wc = swc
        else:
            current.append(sent)
            current_wc += swc
    if current:
        chunks.append(" ".join(current))
    return chunks


PASS2_WORD_THRESHOLD = 40

PASS2_SPLIT_PROMPT = """You are splitting a single long sentence into 2-3 shorter segments for a text-to-speech engine.

Split this text at natural conjunction or preposition boundaries (and, but, or, so, yet, because, though, while, in, on, at, with, from, to, through, across, before, after, etc.). Each sub-segment should read naturally when spoken aloud.

RULES:
- Split into 2-3 segments only
- Split ONLY at conjunction or preposition boundaries
- Preserve the EXACT original text — do not paraphrase, summarize, or omit words
- Every word from the input must appear in exactly one output segment

Return ONLY a JSON object:
{
  "segments": [
    {"text": "first part of the sentence"},
    {"text": "second part of the sentence"}
  ]
}"""


async def _split_overlength_segments(
    segments: list[dict],
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
) -> list[dict]:
    result = []
    for seg in segments:
        text = seg.get("text", "")
        word_count = len(text.split())

        if word_count <= PASS2_WORD_THRESHOLD:
            result.append(seg)
            continue

        try:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": PASS2_SPLIT_PROMPT},
                        {"role": "user", "content": f"Split this text ({word_count} words) into 2-3 segments:\n\n{text}"},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2048,
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

            parsed = json.loads(content.strip())
            sub_segments = parsed.get("segments", [])

            if isinstance(sub_segments, list) and len(sub_segments) > 1:
                original_words = " ".join(text.split()).lower()
                reconstructed_words = " ".join(" ".join(s.get("text", "") for s in sub_segments).split()).lower()

                if original_words == reconstructed_words:
                    for sub in sub_segments:
                        sub_text = sub.get("text", "").strip()
                        if sub_text:
                            result.append({
                                "type": seg.get("type", "narration"),
                                "text": sub_text,
                                "speaker": seg.get("speaker"),
                                "emotion": seg.get("emotion", "neutral"),
                            })
                    continue
                else:
                    logger.warning("Pass 2 split failed integrity check — words were altered. Keeping original segment.")
        except Exception as e:
            logger.warning(f"Pass 2 split failed for segment, keeping original: {e}")

        result.append(seg)

    return result


def _normalize_llm_response(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("LLM response is not a dict")

    flat_segments = []

    if "chunks" in data and isinstance(data["chunks"], list):
        for chunk in data["chunks"]:
            if not isinstance(chunk, dict):
                continue
            segs = chunk.get("segments", [])
            if not isinstance(segs, list):
                continue
            flat_segments.extend(segs)

    if not flat_segments and "segments" in data and isinstance(data["segments"], list):
        flat_segments = data["segments"]

    if not flat_segments:
        raise ValueError("LLM response has no 'segments' or 'chunks' array")

    normalized = []
    detected_speakers = set()

    if isinstance(data.get("characters"), list):
        for c in data["characters"]:
            if isinstance(c, str) and c.strip():
                detected_speakers.add(c.strip())

    if isinstance(data.get("detectedSpeakers"), list):
        for s in data["detectedSpeakers"]:
            if isinstance(s, str) and s.strip():
                detected_speakers.add(s.strip())

    for seg in flat_segments:
        if not isinstance(seg, dict):
            continue
        text = seg.get("text", "")
        if not isinstance(text, str):
            text = str(text) if text else ""
        text = text.strip()
        if not text:
            continue

        seg_type = str(seg.get("type", "narration")).lower().strip()
        if seg_type in ("spoken", "dialog"):
            seg_type = "dialogue"
        if seg_type not in ("narration", "dialogue"):
            seg_type = "narration"

        speaker = seg.get("speaker")
        if not speaker and "speaker_candidates" in seg:
            candidates = seg["speaker_candidates"]
            if isinstance(candidates, dict) and candidates:
                try:
                    speaker = max(candidates, key=lambda k: float(candidates[k]) if candidates[k] is not None else 0)
                except (TypeError, ValueError):
                    speaker = next(iter(candidates))
            elif isinstance(candidates, list) and candidates:
                speaker = candidates[0] if isinstance(candidates[0], str) else None

        if speaker is not None:
            speaker = str(speaker).strip() or None

        if speaker:
            detected_speakers.add(speaker)

        emotion_data = seg.get("emotion", "neutral")
        if isinstance(emotion_data, dict):
            emotion = str(emotion_data.get("label", "neutral"))
        else:
            emotion = str(emotion_data) if emotion_data else "neutral"
        emotion = emotion.lower().strip()
        if emotion not in CANONICAL_EMOTIONS:
            emotion = "neutral"

        normalized.append({
            "type": seg_type,
            "text": text,
            "speaker": speaker,
            "emotion": emotion,
        })

    if not normalized:
        raise ValueError("LLM response produced no valid segments")

    return {
        "segments": normalized,
        "detectedSpeakers": sorted(detected_speakers),
    }


async def _call_llm_for_section(
    client: httpx.AsyncClient,
    section_text: str,
    known_speakers: list[str],
    context: str,
    model: str,
    base_url: str,
    api_key: str,
) -> dict:
    speaker_hint = ""
    if known_speakers:
        speaker_hint = f"\nKnown speakers from previous sections: {', '.join(known_speakers)}. Use these names when you recognize the same characters.\n"

    saved_prompt = _load_prompt()
    emotions_str = ", ".join(CANONICAL_EMOTIONS)

    if not saved_prompt:
        raise ValueError("No parsing prompt configured. Please set one in Settings.")

    prompt_body = saved_prompt.replace("${VALID_EMOTIONS}", emotions_str)
    prompt = f"""{prompt_body}
{speaker_hint}
Previous context: {context[:500] if context else 'Start of text'}

TEXT TO ANALYZE:
{section_text}

Return ONLY valid JSON, no markdown fences."""

    try:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a text analysis assistant. Always respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            timeout=90.0,
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

        raw_result = json.loads(content.strip())
        result = _normalize_llm_response(raw_result)

        result["segments"] = await _split_overlength_segments(
            result.get("segments", []), client, base_url, api_key, model
        )

        return result
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}\nRaw content: {content[:500] if content else '(empty)'}")
        raise
    except Exception as e:
        logger.error(f"LLM call failed for section: {e}")
        raise


def _split_section_by_chunk_count(db, section, max_chunks: int = MAX_CHUNKS_PER_SECTION):
    chunks = db.query(ProjectChunk).filter(
        ProjectChunk.section_id == section.id
    ).order_by(ProjectChunk.chunk_index).all()

    if len(chunks) <= max_chunks:
        return [section]

    new_sections = []
    chunk_groups = []
    for i in range(0, len(chunks), max_chunks):
        chunk_groups.append(chunks[i:i + max_chunks])

    if chunk_groups:
        section.raw_text = "\n".join(c.text for c in chunk_groups[0])
    new_sections.append(section)

    base_section_index = section.section_index

    for group_idx, group in enumerate(chunk_groups[1:], start=1):
        split_raw_text = "\n".join(c.text for c in group) if group else None
        new_section = ProjectSection(
            id=str(uuid.uuid4()),
            chapter_id=section.chapter_id,
            section_index=base_section_index + group_idx,
            raw_text=split_raw_text,
            status="segmented",
        )
        db.add(new_section)
        db.flush()

        for chunk in group:
            chunk.section_id = new_section.id

        new_sections.append(new_section)

    db.commit()
    return new_sections


def _reindex_sections(db, chapter_id: str):
    sections = db.query(ProjectSection).filter(
        ProjectSection.chapter_id == chapter_id
    ).order_by(ProjectSection.section_index, ProjectSection.created_at).all()

    for idx, section in enumerate(sections):
        section.section_index = idx
    db.commit()


def _generate_section_titles(db, chapter_id: str, model: str = "openai/gpt-4.1-mini"):
    base_url = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    api_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")

    if not api_key:
        logger.info("OpenRouter not configured, skipping section title generation")
        return

    sections = db.query(ProjectSection).filter(
        ProjectSection.chapter_id == chapter_id,
        ProjectSection.status == "segmented"
    ).order_by(ProjectSection.section_index).all()

    if not sections:
        return

    section_previews = []
    for sec in sections:
        chunks = db.query(ProjectChunk).filter(
            ProjectChunk.section_id == sec.id
        ).order_by(ProjectChunk.chunk_index).all()

        words = []
        for chunk in chunks:
            words.extend(chunk.text.split())
            if len(words) >= 100:
                break
        preview = " ".join(words[:100])
        section_previews.append(f"Section {sec.section_index + 1}: {preview}")

    prompt = (
        "You are summarizing sections of a book chapter for an audiobook project.\n"
        "For each section below, write an extremely brief summary (5-8 words max) "
        "describing what happens. Use present tense. Be specific about characters and events.\n"
        "Return a JSON array of strings, one title per section, in order.\n\n"
        + "\n\n".join(section_previews)
    )

    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        titles = parsed if isinstance(parsed, list) else parsed.get("titles", parsed.get("sections", []))

        if not isinstance(titles, list):
            logger.warning("LLM returned unexpected format for section titles")
            return

        for i, sec in enumerate(sections):
            if i < len(titles) and titles[i]:
                sec.title = str(titles[i])[:200]

        db.commit()
        logger.info(f"Generated {len(titles)} section titles for chapter {chapter_id}")

    except Exception as e:
        logger.warning(f"Failed to generate section titles: {e}")


def _build_flat_segments(result_segments: list[dict]) -> list[dict]:
    """Expand LLM segments through rechunking into a flat list of chunk dicts."""
    flat = []
    for seg in result_segments:
        seg_text = seg.get("text", "")
        seg_type = seg.get("type", "narration")
        seg_speaker = seg.get("speaker")
        emotion = seg.get("emotion", seg.get("sentiment", "neutral"))
        if emotion not in CANONICAL_EMOTIONS:
            emotion = "neutral"
        for st in _rechunk_segment(seg_text):
            flat.append({
                "type": seg_type,
                "text": st.strip(),
                "speaker": seg_speaker,
                "emotion": emotion,
            })
    return flat


def _merge_short_chunks(segments: list[dict]) -> list[dict]:
    """
    Post-process a flat segment list in three passes, then strip stragglers.

    Each pass (×3):
      For every chunk that is punctuation-only OR has ≤3 words, attempt to
      merge it with the nearest same-speaker neighbour (prev preferred over next).
      Chunks with no same-speaker neighbour are left in place for the next pass.

    Three explicit passes let runs of short chunks (e.g. three 1-word chunks)
    cascade fully: pass 1 folds chunk 1 into chunk 2, pass 2 folds the
    2-word result into chunk 3, pass 3 confirms stability.

    After the three passes, any remaining punctuation-only chunks that could
    not be merged are deleted outright.
    """
    if not segments:
        return segments

    def _is_punct_only(text: str) -> bool:
        return bool(text.strip()) and not re.search(r"[a-zA-Z0-9]", text)

    def _join(a: str, b: str) -> str:
        """Join two texts; skip the space when b opens with punctuation."""
        a = a.rstrip()
        b = b.strip()
        if b and b[0] in ".,!?;:)]\'\"-":
            return a + b
        return a + " " + b

    segs = [dict(s) for s in segments]

    for _ in range(3):
        out: list[dict] = []
        i = 0

        while i < len(segs):
            seg = segs[i]
            text = seg.get("text", "").strip()
            punct_only = _is_punct_only(text)
            short = not punct_only and len(text.split()) <= 3

            if not punct_only and not short:
                out.append(seg)
                i += 1
                continue

            prev = out[-1] if out else None
            nxt = segs[i + 1] if i + 1 < len(segs) else None

            my_speaker = seg.get("speaker")
            prev_same = prev is not None and prev.get("speaker") == my_speaker
            nxt_same = nxt is not None and nxt.get("speaker") == my_speaker

            if prev_same:
                prev["text"] = _join(prev["text"], text)
            elif nxt_same:
                merged = dict(nxt)
                merged["text"] = _join(text, nxt["text"])
                segs[i + 1] = merged
            else:
                # No same-speaker neighbour this pass — leave for next pass
                out.append(seg)

            i += 1

        segs = out

    # Delete any punctuation-only chunks that survived all three passes
    segs = [s for s in segs if not _is_punct_only(s.get("text", "").strip())]

    return segs


async def rechunk_section(project_id: str, section_id: str, model: str = DEFAULT_MODEL):
    """Re-chunk a single section using the same context the LLM had during original segmentation."""
    base_url = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    api_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")

    if not api_key:
        raise ValueError("OpenRouter API key not configured")

    db = get_db_session()
    try:
        section = db.query(ProjectSection).filter(ProjectSection.id == section_id).first()
        if not section:
            raise ValueError("Section not found")

        chapter = db.query(ProjectChapter).filter(ProjectChapter.id == section.chapter_id).first()
        if not chapter or chapter.project_id != project_id:
            raise ValueError("Section does not belong to this project")

        section_text = section.raw_text
        if not section_text:
            raise ValueError("Section has no raw text stored — it was created before this feature was added. Please re-segment the entire project.")

        known_speakers: list[str] = []
        context = ""

        all_chapters = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).order_by(ProjectChapter.chapter_index).all()

        for ch in all_chapters:
            if ch.chapter_index > chapter.chapter_index:
                break
            ch_sections = db.query(ProjectSection).filter(
                ProjectSection.chapter_id == ch.id,
            ).order_by(ProjectSection.section_index).all()
            for sec in ch_sections:
                if ch.id == chapter.id and sec.section_index >= section.section_index:
                    break
                chunks = db.query(ProjectChunk).filter(
                    ProjectChunk.section_id == sec.id
                ).order_by(ProjectChunk.chunk_index).all()
                for chunk in chunks:
                    speaker = chunk.speaker_override or chunk.speaker
                    if speaker and speaker not in known_speakers:
                        known_speakers.append(speaker)
                if sec.raw_text:
                    context = sec.raw_text[-500:] if len(sec.raw_text) > 500 else sec.raw_text

        section.status = "processing"
        section.error_message = None
        db.commit()

        max_attempts = 3
        last_error = None

        async with httpx.AsyncClient() as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    result = await _call_llm_for_section(
                        client, section_text, known_speakers,
                        context, model, base_url, api_key
                    )

                    new_chunks = []
                    new_speakers = []
                    for speaker in result.get("detectedSpeakers", []):
                        if speaker and speaker not in known_speakers:
                            new_speakers.append(speaker)

                    flat = _merge_short_chunks(_build_flat_segments(result.get("segments", [])))
                    for chunk_idx, seg in enumerate(flat):
                        wc = len(seg["text"].split())
                        new_chunks.append(ProjectChunk(
                            id=str(uuid.uuid4()),
                            section_id=section.id,
                            chunk_index=chunk_idx,
                            text=seg["text"],
                            segment_type=seg["type"],
                            speaker=seg["speaker"],
                            emotion=seg["emotion"],
                            word_count=wc,
                            approx_duration_seconds=round(wc / WORDS_PER_SECOND, 1),
                        ))
                    chunk_idx = len(flat)

                    db.query(ProjectChunk).filter(ProjectChunk.section_id == section.id).delete()
                    for chunk in new_chunks:
                        db.add(chunk)

                    section.status = "segmented"
                    section.error_message = None
                    db.commit()

                    _split_section_by_chunk_count(db, section)
                    _reindex_sections(db, chapter.id)

                    last_error = None
                    return {"success": True, "chunksCreated": chunk_idx, "newSpeakers": new_speakers}

                except Exception as e:
                    last_error = e
                    db.rollback()
                    if attempt < max_attempts:
                        logger.warning(f"Re-chunk attempt {attempt}/{max_attempts} failed for section {section_id}: {e}. Retrying...")
                        await asyncio.sleep(1)
                    else:
                        logger.error(f"All {max_attempts} re-chunk attempts failed for section {section_id}: {e}")

        section.status = "failed"
        section.error_message = f"Re-chunk failed after {max_attempts} attempts: {last_error}"
        db.commit()
        raise ValueError(f"Re-chunk failed after {max_attempts} attempts: {last_error}")

    finally:
        db.close()


def apply_merge_short_chunks(project_id: str) -> int:
    """
    Run _merge_short_chunks post-processing on all already-segmented sections of a project.
    Returns the number of chunks eliminated by merging.
    """
    db = get_db_session()
    try:
        chapters = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).order_by(ProjectChapter.chapter_index).all()

        eliminated = 0
        for chapter in chapters:
            sections = (
                db.query(ProjectSection)
                .filter(
                    ProjectSection.chapter_id == chapter.id,
                    ProjectSection.status == "segmented",
                )
                .order_by(ProjectSection.section_index)
                .all()
            )
            for section in sections:
                chunks = (
                    db.query(ProjectChunk)
                    .filter(ProjectChunk.section_id == section.id)
                    .order_by(ProjectChunk.chunk_index)
                    .all()
                )
                if not chunks:
                    continue

                seg_dicts = [
                    {
                        "type": c.segment_type,
                        "text": c.text,
                        "speaker": c.speaker,
                        "emotion": c.emotion,
                    }
                    for c in chunks
                ]
                merged = _merge_short_chunks(seg_dicts)
                if len(merged) == len(chunks):
                    continue  # nothing changed

                eliminated += len(chunks) - len(merged)
                db.query(ProjectChunk).filter(ProjectChunk.section_id == section.id).delete()
                if not merged:
                    # All chunks were deleted — remove the empty section too
                    db.delete(section)
                else:
                    for idx, seg in enumerate(merged):
                        wc = len(seg["text"].split())
                        db.add(ProjectChunk(
                            id=str(uuid.uuid4()),
                            section_id=section.id,
                            chunk_index=idx,
                            text=seg["text"],
                            segment_type=seg["type"],
                            speaker=seg["speaker"],
                            emotion=seg["emotion"],
                            word_count=wc,
                            approx_duration_seconds=round(wc / WORDS_PER_SECOND, 1),
                        ))
                db.commit()

        return eliminated
    finally:
        db.close()


def segment_project_background(project_id: str, model: str = DEFAULT_MODEL, merge_short_chunks: bool = True):
    thread = threading.Thread(
        target=_run_segmentation_wrapper,
        args=(project_id, model, merge_short_chunks),
        daemon=True
    )
    thread.start()
    return thread


def _run_segmentation_wrapper(project_id: str, model: str, merge_short_chunks: bool = True):
    asyncio.run(_run_segmentation(project_id, model, merge_short_chunks))


async def _run_segmentation(project_id: str, model: str, merge_short_chunks: bool = True):
    base_url = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    api_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")

    if not api_key:
        db = get_db_session()
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.status = "failed"
                project.error_message = "OpenRouter API key not configured. Please set up the AI integration in Settings."
                db.commit()
        finally:
            db.close()
        logger.error(f"Project {project_id} segmentation failed: OpenRouter API key not configured")
        return

    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            logger.error(f"Project {project_id} not found")
            return

        project.status = "segmenting"
        project.segmentation_started_at = datetime.utcnow()
        db.commit()

        chapters = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).order_by(ProjectChapter.chapter_index).all()

        all_known_speakers: list[str] = []

        async with httpx.AsyncClient() as client:
            for chapter in chapters:
                try:
                    chapter.status = "segmenting"
                    _chapter_chars_in_progress[project_id] = 0
                    db.commit()

                    section_texts = split_into_sections(chapter.raw_text)

                    all_chapter_sections = []
                    context = ""

                    for sec_idx, section_text in enumerate(section_texts):
                        section = ProjectSection(
                            id=str(uuid.uuid4()),
                            chapter_id=chapter.id,
                            section_index=sec_idx,
                            raw_text=section_text,
                            status="processing",
                        )
                        db.add(section)
                        db.commit()

                        max_attempts = 3
                        last_error = None

                        for attempt in range(1, max_attempts + 1):
                            try:
                                result = await _call_llm_for_section(
                                    client, section_text, all_known_speakers,
                                    context, model, base_url, api_key
                                )

                                for speaker in result.get("detectedSpeakers", []):
                                    if speaker and speaker not in all_known_speakers:
                                        all_known_speakers.append(speaker)

                                flat = _build_flat_segments(result.get("segments", []))
                                if merge_short_chunks:
                                    flat = _merge_short_chunks(flat)
                                for chunk_section_index, seg in enumerate(flat):
                                    wc = len(seg["text"].split())
                                    chunk = ProjectChunk(
                                        id=str(uuid.uuid4()),
                                        section_id=section.id,
                                        chunk_index=chunk_section_index,
                                        text=seg["text"],
                                        segment_type=seg["type"],
                                        speaker=seg["speaker"],
                                        emotion=seg["emotion"],
                                        word_count=wc,
                                        approx_duration_seconds=round(wc / WORDS_PER_SECOND, 1),
                                    )
                                    db.add(chunk)
                                    _chapter_chars_in_progress[project_id] = (
                                        _chapter_chars_in_progress.get(project_id, 0) + len(seg["text"])
                                    )

                                context = section_text[-500:] if len(section_text) > 500 else section_text

                                section.status = "segmented"
                                section.error_message = None
                                db.commit()

                                result_sections = _split_section_by_chunk_count(db, section)
                                all_chapter_sections.extend(result_sections)
                                last_error = None
                                break

                            except Exception as e:
                                last_error = e
                                db.rollback()
                                db.query(ProjectChunk).filter(ProjectChunk.section_id == section.id).delete()
                                db.commit()
                                if attempt < max_attempts:
                                    logger.warning(f"Attempt {attempt}/{max_attempts} failed for section {sec_idx} of chapter {chapter.chapter_index}: {e}. Retrying...")
                                    await asyncio.sleep(1)
                                else:
                                    logger.error(f"All {max_attempts} attempts failed for section {sec_idx} of chapter {chapter.chapter_index}: {e}")

                        if last_error is not None:
                            section.status = "failed"
                            section.error_message = f"Failed after {max_attempts} attempts: {last_error}"
                            db.commit()
                            all_chapter_sections.append(section)

                    _reindex_sections(db, chapter.id)

                    try:
                        _generate_section_titles(db, chapter.id, model=model)
                    except Exception as e:
                        logger.warning(f"Section title generation failed for chapter {chapter.chapter_index}: {e}")

                    if all_known_speakers:
                        chapter.speakers_json = json.dumps(all_known_speakers)

                    failed_sections = sum(1 for s in all_chapter_sections if s.status == "failed")
                    if failed_sections == len(all_chapter_sections) and all_chapter_sections:
                        chapter.status = "failed"
                        chapter.error_message = "All sections failed to segment"
                    else:
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
        _chapter_chars_in_progress.pop(project_id, None)
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
