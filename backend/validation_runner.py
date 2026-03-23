"""
Audio Validation Runner
Runs STT on generated chunk audio and computes text similarity scores.
"""
import asyncio
import base64
import difflib
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Fuzzy-matching algorithms (pure stdlib)
# ─────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lower-case, strip non-alphanumeric (keep spaces), collapse whitespace."""
    text = re.sub(r"[^a-z0-9 ]", "", text.lower())
    return re.sub(r"\s+", " ", text).strip()


# ─────────────────────────────────────────────
# Phonetic preprocessing — Double Metaphone
# (pure stdlib, no external deps)
# ─────────────────────────────────────────────

def _dm_word(word: str) -> str:
    """
    Double Metaphone — returns the *primary* phonetic code for a single word.
    Implements the Lawrence Philips algorithm (simplified but faithful to the
    English ruleset that matters for TTS/STT comparison).
    """
    if not word:
        return ""

    word = re.sub(r"[^A-Za-z]", "", word).upper()
    if not word:
        return ""

    # --- initial special cases ---
    if word[:2] in ("AE", "GN", "KN", "PN", "WR"):
        word = word[1:]
    if word[0] == "X":
        word = "S" + word[1:]

    # Vowels at start: encode as "A"
    if word[0] in "AEIOU":
        word = "A" + word[1:]

    result: list[str] = []
    i = 0
    length = len(word)

    def at(*pos_chars: tuple) -> bool:
        """True if word[i+offset] == char (handles bounds)."""
        # Called as at(0,'A') or at(1,'B','C')
        return False  # replaced by inline checks below

    def ch(offset: int) -> str:
        pos = i + offset
        return word[pos] if 0 <= pos < length else ""

    while i < length:
        c = word[i]

        # --- skip duplicate adjacent (except C) ---
        if c != "C" and i > 0 and word[i - 1] == c:
            i += 1
            continue

        if c in "AEIOU":
            if i == 0:
                result.append("A")
            i += 1
            continue

        if c == "B":
            # silent after M at end
            if not (i == length - 1 and ch(-1) == "M"):
                result.append("B")
            i += 1

        elif c == "C":
            pair = word[i:i+2]
            triple = word[i:i+3]
            if pair == "CH":
                result.append("X")  # "ch" → X
                i += 2
            elif pair == "CI" and i + 2 < length and word[i + 2] == "A":
                result.append("X")  # "CIA"
                i += 3
            elif c == "C" and ch(1) in "EIY":
                result.append("S")
                i += 1
            elif pair == "CK":
                result.append("K")
                i += 2
            elif pair == "QU":
                result.append("KW")
                i += 2
            else:
                result.append("K")
                i += 1

        elif c == "D":
            pair = word[i:i+2]
            if pair == "DG" and ch(2) in "EIY":
                result.append("J")
                i += 3
            elif pair == "DT":
                result.append("T")
                i += 2
            else:
                result.append("T")
                i += 1

        elif c == "F":
            result.append("F")
            i += 1

        elif c == "G":
            pair = word[i:i+2]
            if pair == "GH":
                # silent after vowel unless at start
                if i > 0 and word[i - 1] in "AEIOU":
                    pass  # silent
                else:
                    result.append("K")
                i += 2
            elif pair == "GN":
                # GN at end or GNED at end → silent G
                if i + 1 == length - 1 or word[i:i+4] == "GNED":
                    pass
                else:
                    result.append("K")
                    result.append("N")
                i += 2
            elif pair in ("GI", "GE", "GY"):
                result.append("J")
                i += 2
            else:
                result.append("K")
                i += 1

        elif c == "H":
            # H before vowel, not after vowel
            if ch(1) in "AEIOU" and (i == 0 or ch(-1) not in "AEIOU"):
                result.append("H")
            i += 1

        elif c == "J":
            result.append("J")
            i += 1

        elif c == "K":
            if ch(-1) != "C":
                result.append("K")
            i += 1

        elif c == "L":
            result.append("L")
            i += 1

        elif c == "M":
            result.append("M")
            i += 1

        elif c == "N":
            if ch(1) == "N":
                i += 2
            else:
                result.append("N")
                i += 1

        elif c == "P":
            if ch(1) == "H":
                result.append("F")
                i += 2
            else:
                result.append("P")
                i += 1

        elif c == "Q":
            result.append("K")
            i += 1

        elif c == "R":
            result.append("R")
            i += 1

        elif c == "S":
            pair = word[i:i+2]
            triple = word[i:i+3]
            if pair == "SH" or triple in ("SIO", "SIA"):
                result.append("X")
                i += 2 if pair == "SH" else 3
            elif pair == "SC" and ch(2) in "EIY":
                result.append("S")
                i += 3
            else:
                result.append("S")
                i += 1

        elif c == "T":
            pair = word[i:i+2]
            triple = word[i:i+3]
            if pair == "TH":
                result.append("0")   # dental fricative
                i += 2
            elif triple in ("TIA", "TIO"):
                result.append("X")
                i += 3
            elif pair == "TCH":
                result.append("X")
                i += 3
            else:
                result.append("T")
                i += 1

        elif c == "V":
            result.append("F")
            i += 1

        elif c == "W":
            if ch(1) in "AEIOU":
                result.append("W")
            i += 1

        elif c == "X":
            result.append("KS")
            i += 1

        elif c == "Y":
            if ch(1) in "AEIOU":
                result.append("Y")
            i += 1

        elif c == "Z":
            result.append("S")
            i += 1

        else:
            i += 1

    return "".join(result)


def _phonetic_repr(text: str) -> str:
    """
    Convert text to a Double Metaphone phonetic representation.
    Each word is converted independently and the codes are joined with spaces,
    preserving word boundaries so word-level algorithms (WER, token_sort) still work.
    Empty codes (function words like "the") are retained as-is after normalization.
    """
    words = _normalize(text).split()
    codes = []
    for word in words:
        code = _dm_word(word)
        codes.append(code if code else word)  # fall back to normalized word if no code
    return " ".join(codes)


def _sequence_matcher(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _levenshtein(a: str, b: str) -> float:
    """Normalized Levenshtein similarity: 1 - (edit_distance / max_len)."""
    a, b = _normalize(a), _normalize(b)
    if not a and not b:
        return 1.0
    la, lb = len(a), len(b)
    max_len = max(la, lb)
    # Wagner-Fischer DP
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (0 if ca == cb else 1)))
        prev = curr
    return 1.0 - prev[lb] / max_len


def _token_sort(a: str, b: str) -> float:
    """Sort tokens before comparing (order-invariant)."""
    a_sorted = " ".join(sorted(_normalize(a).split()))
    b_sorted = " ".join(sorted(_normalize(b).split()))
    return difflib.SequenceMatcher(None, a_sorted, b_sorted).ratio()


def _jaro_winkler(a: str, b: str) -> float:
    """Jaro-Winkler similarity."""
    a, b = _normalize(a), _normalize(b)
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    match_dist = max(la, lb) // 2 - 1
    if match_dist < 0:
        match_dist = 0
    a_matches = [False] * la
    b_matches = [False] * lb
    matches = 0
    transpositions = 0
    for i in range(la):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, lb)
        for j in range(start, end):
            if b_matches[j] or a[i] != b[j]:
                continue
            a_matches[i] = b_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    a_seq = [a[i] for i in range(la) if a_matches[i]]
    b_seq = [b[j] for j in range(lb) if b_matches[j]]
    for ca, cb in zip(a_seq, b_seq):
        if ca != cb:
            transpositions += 1
    jaro = (matches / la + matches / lb + (matches - transpositions / 2) / matches) / 3
    prefix = 0
    for ca, cb in zip(a[:4], b[:4]):
        if ca != cb:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def _wer_similarity(a: str, b: str) -> float:
    """Word Error Rate based similarity: 1 - WER, clamped to [0, 1]."""
    ref = _normalize(a).split()
    hyp = _normalize(b).split()
    if not ref and not hyp:
        return 1.0
    if not ref:
        return 0.0
    # Edit distance on word level
    r, h = len(ref), len(hyp)
    d = [[0] * (h + 1) for _ in range(r + 1)]
    for i in range(r + 1):
        d[i][0] = i
    for j in range(h + 1):
        d[0][j] = j
    for i in range(1, r + 1):
        for j in range(1, h + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1))
    wer = d[r][h] / r
    return max(0.0, 1.0 - wer)


ALGORITHM_FUNCS = {
    "sequence_matcher": _sequence_matcher,
    "levenshtein": _levenshtein,
    "token_sort": _token_sort,
    "jaro_winkler": _jaro_winkler,
    "wer": _wer_similarity,
}

ALGORITHM_LABELS = {
    "sequence_matcher": "SequenceMatcher",
    "levenshtein": "Levenshtein",
    "token_sort": "Token Sort",
    "jaro_winkler": "Jaro-Winkler",
    "wer": "WER Similarity",
}


def _processed_text(text: str, phonetic: bool) -> str:
    """Return the form of *text* that is actually passed to similarity algorithms."""
    if phonetic:
        return _phonetic_repr(text)
    return _normalize(text)


def compute_scores(source_text: str, stt_text: str, algorithms: list[str], phonetic: bool = False) -> dict[str, float]:
    if phonetic:
        source_text = _phonetic_repr(source_text)
        stt_text = _phonetic_repr(stt_text)
    scores = {}
    for algo in algorithms:
        fn = ALGORITHM_FUNCS.get(algo)
        if fn:
            try:
                scores[algo] = round(fn(source_text, stt_text), 4)
            except Exception:
                scores[algo] = 0.0
    return scores


def combine_scores(scores: dict[str, float], method: str, drop_worst_n: int) -> float:
    values = list(scores.values())
    if not values:
        return 0.0
    if drop_worst_n > 0 and len(values) > drop_worst_n:
        values = sorted(values)[drop_worst_n:]
    if not values:
        return 0.0
    if method == "max":
        return max(values)
    if method == "min":
        return min(values)
    return sum(values) / len(values)  # average (default)


# ─────────────────────────────────────────────
# STT via OpenRouter
# ─────────────────────────────────────────────

def _is_stt_model(model: str) -> bool:
    """Return True for dedicated STT models that use /audio/transcriptions (Whisper variants)."""
    lower = model.lower()
    return "whisper" in lower or lower.endswith("-stt") or "/stt" in lower


async def _transcribe_audio(audio_bytes: bytes, model: str, mime: str = "audio/mpeg") -> str:
    """Send audio to OpenRouter and return the transcript.

    Routes to the correct endpoint depending on model type:
    - Dedicated STT models (Whisper etc.) → POST /audio/transcriptions  (multipart form)
    - Multimodal LLMs (Gemini, GPT-4o …)  → POST /chat/completions      (JSON + base64)
    """
    openrouter_base = os.environ.get("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    openrouter_key = os.environ.get("AI_INTEGRATIONS_OPENROUTER_API_KEY", "")
    if not openrouter_key:
        raise RuntimeError("OpenRouter API key not configured")

    auth_headers = {"Authorization": f"Bearer {openrouter_key}"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        if _is_stt_model(model):
            # Whisper-style models: multipart form upload to /audio/transcriptions
            resp = await client.post(
                f"{openrouter_base}/audio/transcriptions",
                headers=auth_headers,
                files={"file": ("audio.mp3", audio_bytes, mime)},
                data={"model": model},
            )
            resp.raise_for_status()
            return (resp.json().get("text") or "").strip()
        else:
            # Multimodal LLM: send base64-encoded audio inside a chat message
            audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Transcribe the following audio clip exactly as spoken. "
                                "Output only the verbatim transcript with no commentary, "
                                "punctuation notes, or formatting. If the audio is silent or "
                                "unintelligible, output an empty string."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{audio_b64}"},
                        },
                    ],
                }
            ]
            resp = await client.post(
                f"{openrouter_base}/chat/completions",
                headers={**auth_headers, "Content-Type": "application/json"},
                json={"model": model, "messages": messages},
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"] or ""
            return content.strip()


# ─────────────────────────────────────────────
# Background validation job
# ─────────────────────────────────────────────

def run_validation_background(project_id: str, job_id: str, config: dict):
    """Spawn a daemon thread to run validation for a project."""
    thread = threading.Thread(
        target=_run_validation_sync,
        args=(project_id, job_id, config),
        daemon=True,
    )
    thread.start()
    return thread


def _run_validation_sync(project_id: str, job_id: str, config: dict):
    asyncio.run(_run_validation_async(project_id, job_id, config))


async def _run_validation_async(project_id: str, job_id: str, config: dict):
    from database import (
        get_db_session, TTSJob, JobStatus, ProjectChunk, ProjectSection,
        ProjectChapter, ProjectAudioFile, ChunkValidationResult,
        ValidationHistory, ValidationAlgorithmScore,
    )

    stt_model = config.get("stt_model", "google/gemini-2.5-flash")
    algorithms = config.get("algorithms", ["sequence_matcher", "levenshtein", "token_sort"])
    combination_method = config.get("combination_method", "average")
    drop_worst_n = config.get("drop_worst_n", 0)
    cutoff = config.get("similarity_cutoff", 0.80)
    auto_regenerate = config.get("auto_regenerate", False)
    use_phonetic = config.get("use_phonetic", False)

    db = get_db_session()
    try:
        job = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if not job:
            return
        job.status = JobStatus.PROCESSING.value
        db.commit()

        # Collect all chunks with audio for this project
        audio_by_chunk: dict[str, bytes] = {}
        text_by_chunk: dict[str, str] = {}
        audio_files = (
            db.query(ProjectAudioFile)
            .filter(
                ProjectAudioFile.project_id == project_id,
                ProjectAudioFile.scope_type == "chunk",
            )
            .all()
        )
        for af in audio_files:
            if af.scope_id not in audio_by_chunk:
                data: Optional[bytes] = None
                if af.audio_data:
                    data = af.audio_data
                elif af.file_path and os.path.exists(af.file_path):
                    with open(af.file_path, "rb") as fh:
                        data = fh.read()
                if data:
                    audio_by_chunk[af.scope_id] = data

        # Collect chunk text
        chunks = (
            db.query(ProjectChunk)
            .join(ProjectSection, ProjectChunk.section_id == ProjectSection.id)
            .join(ProjectChapter, ProjectSection.chapter_id == ProjectChapter.id)
            .filter(ProjectChapter.project_id == project_id)
            .order_by(ProjectChapter.chapter_index, ProjectSection.section_index, ProjectChunk.chunk_index)
            .all()
        )
        for c in chunks:
            text_by_chunk[c.id] = c.text

        chunk_ids_with_audio = [c.id for c in chunks if c.id in audio_by_chunk]

        job.total_segments = len(chunk_ids_with_audio)
        job.completed_segments = 0
        job.failed_segments = 0
        db.commit()
    finally:
        db.close()

    # Delete any previous validation results for this project
    db = get_db_session()
    try:
        db.query(ChunkValidationResult).filter(ChunkValidationResult.project_id == project_id).delete()
        db.commit()
    finally:
        db.close()

    flagged_chunk_ids: list[str] = []

    for chunk_id in chunk_ids_with_audio:
        source_text = text_by_chunk.get(chunk_id, "")
        audio_bytes = audio_by_chunk[chunk_id]

        stt_text = None
        scores: dict[str, float] = {}
        combined = 0.0
        flagged = False

        processed_src = None
        processed_stt = None
        try:
            stt_text = await _transcribe_audio(audio_bytes, stt_model)
            processed_src = _processed_text(source_text, use_phonetic)
            processed_stt = _processed_text(stt_text, use_phonetic)
            scores = compute_scores(source_text, stt_text, algorithms, phonetic=use_phonetic)
            combined = combine_scores(scores, combination_method, drop_worst_n)
            flagged = combined < cutoff
        except Exception as exc:
            logger.error(f"Validation failed for chunk {chunk_id}: {exc}")
            stt_text = f"[ERROR: {exc}]"
            flagged = True  # flag on error so user can inspect

        if flagged:
            flagged_chunk_ids.append(chunk_id)

        db = get_db_session()
        try:
            result = ChunkValidationResult(
                id=str(uuid.uuid4()),
                project_id=project_id,
                chunk_id=chunk_id,
                job_id=job_id,
                stt_text=stt_text,
                processed_source_text=processed_src,
                processed_stt_text=processed_stt,
                algorithm_scores=json.dumps(scores),
                combined_score=combined,
                is_flagged=flagged,
                is_regenerated=False,
            )
            db.add(result)

            # Write permanent history row
            src_words = source_text.split() if source_text else []
            stt_words = stt_text.split() if stt_text else []
            history = ValidationHistory(
                id=str(uuid.uuid4()),
                project_id=project_id,
                chunk_id=chunk_id,
                validation_job_id=job_id,
                source_text=source_text,
                stt_text=stt_text,
                source_char_length=len(source_text) if source_text else None,
                stt_char_length=len(stt_text) if stt_text else None,
                source_word_count=len(src_words),
                stt_word_count=len(stt_words),
                use_phonetic=use_phonetic,
                combined_score=combined if scores else None,
                combination_method=combination_method,
                drop_worst_n=drop_worst_n,
                similarity_cutoff=cutoff,
                is_flagged=flagged,
                is_good=False,
                is_regenerated=False,
                regen_type=None,
            )
            db.add(history)
            db.flush()  # populate history.id before adding child rows
            for algo, score_val in scores.items():
                db.add(ValidationAlgorithmScore(
                    id=str(uuid.uuid4()),
                    history_id=history.id,
                    algorithm=algo,
                    score=score_val,
                ))

            job_row = db.query(TTSJob).filter(TTSJob.id == job_id).first()
            if job_row:
                job_row.completed_segments += 1
            db.commit()
        finally:
            db.close()

    # Mark job complete
    db = get_db_session()
    try:
        job_row = db.query(TTSJob).filter(TTSJob.id == job_id).first()
        if job_row:
            job_row.status = JobStatus.COMPLETED.value
        db.commit()
    finally:
        db.close()

    # Auto-regenerate if requested
    if auto_regenerate and flagged_chunk_ids:
        await _regenerate_chunks(project_id, flagged_chunk_ids, job_id=job_id)


async def _regenerate_chunks(project_id: str, chunk_ids: list[str], job_id: str | None = None):
    """Submit flagged chunks for TTS re-generation and mark them as regenerated."""
    import httpx as _httpx
    from database import get_db_session, ChunkValidationResult, ValidationHistory

    try:
        async with _httpx.AsyncClient(timeout=30.0) as client:
            # Use internal API to trigger generation
            # We call the generate endpoint for each chunk individually
            for chunk_id in chunk_ids:
                try:
                    await client.post(
                        f"http://127.0.0.1:8000/projects/{project_id}/generate",
                        json={"scopeType": "chunk", "scopeId": chunk_id, "onlyMissing": False},
                    )
                except Exception as exc:
                    logger.error(f"Auto-regenerate failed for chunk {chunk_id}: {exc}")
    except Exception as exc:
        logger.error(f"Auto-regenerate setup failed: {exc}")

    # Mark all as regenerated regardless (optimistic)
    db = get_db_session()
    try:
        db.query(ChunkValidationResult).filter(
            ChunkValidationResult.project_id == project_id,
            ChunkValidationResult.chunk_id.in_(chunk_ids),
        ).update({"is_regenerated": True}, synchronize_session=False)
        # Stamp history rows from this specific validation run
        history_q = db.query(ValidationHistory).filter(
            ValidationHistory.project_id == project_id,
            ValidationHistory.chunk_id.in_(chunk_ids),
        )
        if job_id:
            history_q = history_q.filter(ValidationHistory.validation_job_id == job_id)
        history_q.update(
            {"is_regenerated": True, "regen_type": "auto"},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()
