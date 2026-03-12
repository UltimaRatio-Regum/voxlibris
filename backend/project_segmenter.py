import uuid
import re
import json
import logging
import os
import asyncio
import threading
from typing import Optional, List
from pathlib import Path

import httpx

from database import (
    get_db_session, Project, ProjectChapter, ProjectSection, ProjectChunk
)

logger = logging.getLogger(__name__)

SECTION_WORD_LIMIT = 300
MAX_CHUNKS_PER_SECTION = 30
WORDS_PER_SECOND = 2.5

DEFAULT_MODEL = "openai/gpt-4.1-mini"

CANONICAL_EMOTIONS = [
    "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
    "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
]

PARSING_PROMPT_FILE = Path("parsing_prompt_settings.json")


def _load_custom_prompt() -> Optional[str]:
    if PARSING_PROMPT_FILE.exists():
        try:
            with open(PARSING_PROMPT_FILE, "r") as f:
                data = json.load(f)
            if data.get("prompt"):
                return data["prompt"]
        except Exception as e:
            logger.warning(f"Failed to load custom parsing prompt: {e}")
    return None


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


def _rechunk_segment(text: str, max_words: int = 30) -> list[str]:
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

    custom_prompt = _load_custom_prompt()
    emotions_str = ", ".join(CANONICAL_EMOTIONS)

    if custom_prompt:
        prompt_body = custom_prompt.replace("${VALID_EMOTIONS}", emotions_str)
        prompt = f"""{prompt_body}
{speaker_hint}
Previous context: {context[:500] if context else 'Start of text'}

TEXT TO ANALYZE:
{section_text}

Return ONLY valid JSON, no markdown fences."""
    else:
        prompt = f"""You are chunking text for a text-to-speech audiobook engine. Each chunk will be sent to a TTS engine as a separate audio clip, so chunk size directly controls audio segment length.

TARGET: Aim for chunks of roughly 25 words (~10 seconds of speech). Chunks may be shorter or up to ~40 words when needed. The most important rule is that every chunk must break at a NATURAL PAUSE POINT — a place where a human reader would briefly pause.

NATURAL PAUSE PRIORITY — THIS IS THE MOST IMPORTANT RULE:
Always break chunks at natural speech boundaries. A shorter or longer chunk that ends at a natural pause is ALWAYS better than one that hits a word-count target but breaks mid-thought. Do NOT greedily pack words up to a limit — look ahead and choose the break point that sounds most natural when read aloud.

Preferred break points (best to worst):
1. Sentence boundaries (periods, question marks, exclamation marks)
2. Semicolons, colons, or em-dashes
3. Before conjunctions (and, but, or, so, yet, because, though, while)
4. Before prepositional phrases (in, on, at, with, from, to, through, across, etc.)
5. Commas

BAD vs GOOD example:
Given: "This is a short sentence. I'm going to ramble on and on noticing that this is a longer sentence and make sure that the sentence gets broken up at a bad spot instead of a more natural one."

BAD (greedy fill, breaks mid-phrase):
- Chunk 1: "This is a short sentence. I'm going to ramble on and on noticing that this is a longer sentence and make sure that the sentence gets broken up at a bad"
- Chunk 2: "spot instead of a more natural one."

GOOD (respects sentence boundary, even though Chunk 1 is short):
- Chunk 1: "This is a short sentence."
- Chunk 2: "I'm going to ramble on and on noticing that this is a longer sentence and make sure that the sentence gets broken up at a bad spot instead of a more natural one."

ALSO GOOD (splits long sentence at a natural clause boundary):
- Chunk 1: "This is a short sentence."
- Chunk 2: "I'm going to ramble on and on noticing that this is a longer sentence"
- Chunk 3: "and make sure that the sentence gets broken up at a bad spot instead of a more natural one."

CHUNKING RULES:
1. QUOTE BOUNDARIES: Quoted dialogue must always be its own chunk, separate from surrounding narration. Never mix dialogue and narration in one chunk.
2. NATURAL PAUSES FIRST: Always prefer breaking at natural pause points over hitting a word-count target. A 5-word chunk that ends at a sentence boundary is better than a 25-word chunk that breaks mid-clause.
3. SOFT SIZE GUIDE: Target ~25 words per chunk. Chunks under 10 words are fine if they are complete sentences or short dialogue. Chunks up to ~40 words are acceptable if breaking earlier would split a natural phrase. Avoid chunks over 40 words.
4. TYPE: Each chunk is either "narration" or "dialogue", never both.
5. SPEAKER: For dialogue, identify the speaker by name from context. For narration, speaker is null.
6. EMOTION: Assign exactly one emotion per chunk from: {emotions_str}
7. PRESERVE TEXT: Copy the original text exactly — do not paraphrase, summarize, or omit any words.
{speaker_hint}
Previous context: {context[:500] if context else 'Start of text'}

TEXT TO ANALYZE:
{section_text}

Return ONLY a JSON object:
{{
  "segments": [
    {{
      "type": "narration" or "dialogue",
      "text": "exact text from the passage",
      "speaker": "speaker name or null for narration",
      "emotion": "one emotion from the list above"
    }}
  ],
  "detectedSpeakers": ["list", "of", "speaker", "names"]
}}

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

    new_sections.append(section)

    base_section_index = section.section_index

    for group_idx, group in enumerate(chunk_groups[1:], start=1):
        new_section = ProjectSection(
            id=str(uuid.uuid4()),
            chapter_id=section.chapter_id,
            section_index=base_section_index + group_idx,
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


def segment_project_background(project_id: str, model: str = DEFAULT_MODEL):
    thread = threading.Thread(
        target=_run_segmentation_wrapper,
        args=(project_id, model),
        daemon=True
    )
    thread.start()
    return thread


def _run_segmentation_wrapper(project_id: str, model: str):
    asyncio.run(_run_segmentation(project_id, model))


async def _run_segmentation(project_id: str, model: str):
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
        db.commit()

        chapters = db.query(ProjectChapter).filter(
            ProjectChapter.project_id == project_id
        ).order_by(ProjectChapter.chapter_index).all()

        all_known_speakers: list[str] = []

        async with httpx.AsyncClient() as client:
            for chapter in chapters:
                try:
                    chapter.status = "segmenting"
                    db.commit()

                    section_texts = split_into_sections(chapter.raw_text)
                    chunk_global_index = 0

                    all_chapter_sections = []
                    context = ""

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
                            result = await _call_llm_for_section(
                                client, section_text, all_known_speakers,
                                context, model, base_url, api_key
                            )

                            for speaker in result.get("detectedSpeakers", []):
                                if speaker and speaker not in all_known_speakers:
                                    all_known_speakers.append(speaker)

                            for seg in result.get("segments", []):
                                seg_text = seg.get("text", "")
                                seg_type = seg.get("type", "narration")
                                seg_speaker = seg.get("speaker")
                                emotion = seg.get("emotion", seg.get("sentiment", "neutral"))
                                if emotion not in CANONICAL_EMOTIONS:
                                    emotion = "neutral"

                                sub_texts = _rechunk_segment(seg_text)

                                for st in sub_texts:
                                    wc = len(st.split())
                                    chunk = ProjectChunk(
                                        id=str(uuid.uuid4()),
                                        section_id=section.id,
                                        chunk_index=chunk_global_index,
                                        text=st,
                                        segment_type=seg_type,
                                        speaker=seg_speaker,
                                        emotion=emotion,
                                        word_count=wc,
                                        approx_duration_seconds=round(wc / WORDS_PER_SECOND, 1),
                                    )
                                    db.add(chunk)
                                    chunk_global_index += 1

                            context = section_text[-500:] if len(section_text) > 500 else section_text

                            section.status = "segmented"
                            db.commit()

                            result_sections = _split_section_by_chunk_count(db, section)
                            all_chapter_sections.extend(result_sections)

                        except Exception as e:
                            logger.error(f"Failed to segment section {sec_idx} of chapter {chapter.chapter_index}: {e}")
                            section.status = "failed"
                            section.error_message = str(e)
                            db.commit()
                            all_chapter_sections.append(section)

                    _reindex_sections(db, chapter.id)

                    try:
                        _generate_section_titles(db, chapter.id, model=model)
                    except Exception as e:
                        logger.warning(f"Section title generation failed for chapter {chapter.chapter_index}: {e}")

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
