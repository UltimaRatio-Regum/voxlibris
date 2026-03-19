"""
Audio export module for generating downloadable audiobook files.
Supports: single MP3, MP3 per chapter (ZIP), and M4B (AAC with chapters).

Progress callback contract:
  callback(phase: str, current: int, total: int, message: str)
  Phases: "decode", "merge", "encode"
"""
import io
import math
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
import logging
from typing import List, Optional, Tuple, Callable

from pydub import AudioSegment
from mutagen.mp3 import MP3
from mutagen.id3 import (
    ID3, TIT2, TPE1, TPE2, TALB, TCON, TDRC, COMM, TRCK, APIC
)
from mutagen.mp4 import MP4, MP4Cover

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], None]


def _safe_str(value, fallback: str = "") -> str:
    """Return a clean Unicode string, safely decoding bytes if necessary."""
    if value is None:
        return fallback
    if isinstance(value, bytes):
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return value.decode(enc)
            except UnicodeDecodeError:
                continue
        return value.decode("latin-1", errors="replace")
    if isinstance(value, str):
        return value
    return str(value)


def _pairwise_merge(segments: List[AudioSegment]) -> AudioSegment:
    if len(segments) == 0:
        return AudioSegment.empty()
    if len(segments) == 1:
        return segments[0]

    while len(segments) > 1:
        merged = []
        i = 0
        remaining = len(segments)
        while i < remaining:
            if remaining - i == 3:
                merged.append(segments[i] + segments[i + 1] + segments[i + 2])
                i += 3
            elif remaining - i >= 2:
                merged.append(segments[i] + segments[i + 1])
                i += 2
            else:
                merged.append(segments[i])
                i += 1
        segments = merged

    return segments[0]


def _apply_id3_tags(
    mp3_bytes: bytes,
    title: str,
    author: Optional[str] = None,
    narrator: Optional[str] = None,
    genre: Optional[str] = None,
    year: Optional[str] = None,
    description: Optional[str] = None,
    cover_image: Optional[bytes] = None,
    track_number: Optional[str] = None,
    album: Optional[str] = None,
) -> bytes:
    buf = io.BytesIO(mp3_bytes)
    audio = MP3(buf)

    if audio.tags is None:
        audio.add_tags()

    tags = audio.tags
    tags.add(TIT2(encoding=3, text=_safe_str(title)))
    if album:
        tags.add(TALB(encoding=3, text=_safe_str(album)))
    if author:
        tags.add(TPE1(encoding=3, text=_safe_str(author)))
    if narrator:
        tags.add(TPE2(encoding=3, text=_safe_str(narrator)))
    if genre:
        tags.add(TCON(encoding=3, text=_safe_str(genre)))
    if year:
        tags.add(TDRC(encoding=3, text=_safe_str(year)))
    if description:
        tags.add(COMM(encoding=3, lang="eng", desc="", text=_safe_str(description)))
    if track_number:
        tags.add(TRCK(encoding=3, text=_safe_str(track_number)))
    if cover_image:
        mime = "image/jpeg"
        if cover_image[:4] == b'\x89PNG':
            mime = "image/png"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover_image))

    out = io.BytesIO()
    audio.save(out)
    return out.getvalue()


def _build_mp3_segment_with_progress(
    audio_blobs: List[bytes],
    pause_ms: int = 500,
    progress_callback: Optional[ProgressCallback] = None,
    total_blob_label: Optional[int] = None,
    blob_offset: int = 0,
) -> AudioSegment:
    silence = AudioSegment.silent(duration=pause_ms) if pause_ms > 0 else None
    total = max(len(audio_blobs), 1)
    display_total = total_blob_label if total_blob_label is not None else total

    decoded: List[AudioSegment] = []
    for i, blob in enumerate(audio_blobs):
        try:
            seg = AudioSegment.from_file(io.BytesIO(blob))
            if decoded and silence:
                decoded.append(silence)
            decoded.append(seg)
        except Exception as e:
            logger.warning(f"Skipping invalid audio blob (index {i}): {e}")
        if progress_callback:
            current_num = blob_offset + i + 1
            progress_callback(
                "decode", current_num, display_total,
                f"Decoding chunks for processing ({current_num} of {display_total})...",
            )

    if len(decoded) == 0:
        return AudioSegment.empty()

    total_rounds = max(1, math.ceil(math.log2(len(decoded))))
    current_round = 0
    segments = decoded
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
        current_round += 1
        if progress_callback:
            merge_pct = round(current_round / total_rounds * 100)
            progress_callback(
                "merge", current_round, total_rounds,
                f"Merging chunks ({merge_pct}% complete)...",
            )

    return segments[0]


def export_single_mp3(
    chapter_audio: List[Tuple[str, List[bytes]]],
    title: str,
    pause_ms: int = 500,
    author: Optional[str] = None,
    narrator: Optional[str] = None,
    genre: Optional[str] = None,
    year: Optional[str] = None,
    description: Optional[str] = None,
    cover_image: Optional[bytes] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> bytes:
    all_blobs = []
    for _ch_title, blobs in chapter_audio:
        all_blobs.extend(blobs)

    total_blobs = len(all_blobs)

    combined = _build_mp3_segment_with_progress(
        all_blobs, pause_ms, progress_callback,
        total_blob_label=total_blobs,
        blob_offset=0,
    )

    if progress_callback:
        progress_callback("encode", 0, 1, "Encoding audio...")

    buf = io.BytesIO()
    combined.export(buf, format="mp3", bitrate="192k")
    mp3_bytes = buf.getvalue()

    if progress_callback:
        progress_callback("encode", 1, 1, "Applying metadata tags...")

    result = _apply_id3_tags(
        mp3_bytes, title=title, author=author, narrator=narrator,
        genre=genre, year=year, description=description,
        cover_image=cover_image, album=title,
    )
    return result


def export_mp3_per_chapter(
    chapter_audio: List[Tuple[str, List[bytes]]],
    title: str,
    pause_ms: int = 500,
    author: Optional[str] = None,
    narrator: Optional[str] = None,
    genre: Optional[str] = None,
    year: Optional[str] = None,
    description: Optional[str] = None,
    cover_image: Optional[bytes] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> bytes:
    valid_chapters = [(ch_title, blobs) for ch_title, blobs in chapter_audio if blobs]
    total_chapters = max(1, len(valid_chapters))
    total_blobs = sum(len(blobs) for _, blobs in valid_chapters)

    blob_offset = 0
    built_segments = []
    for ci, (ch_title, blobs) in enumerate(valid_chapters):
        combined = _build_mp3_segment_with_progress(
            blobs, pause_ms, progress_callback,
            total_blob_label=total_blobs,
            blob_offset=blob_offset,
        )
        built_segments.append((ch_title, combined))
        blob_offset += len(blobs)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for ci, (ch_title, combined) in enumerate(built_segments):
            if progress_callback:
                progress_callback("encode", ci, total_chapters, f"Encoding chapter {ci + 1} of {total_chapters}...")

            mp3_buf = io.BytesIO()
            combined.export(mp3_buf, format="mp3", bitrate="192k")

            safe_title = ch_title or f"Chapter {ci + 1}"
            safe_title = "".join(c for c in safe_title if c.isalnum() or c in " _-").strip()
            filename = f"{ci + 1:02d} - {safe_title}.mp3"

            tagged = _apply_id3_tags(
                mp3_buf.getvalue(),
                title=safe_title,
                author=author,
                narrator=narrator,
                genre=genre,
                year=year,
                description=description,
                cover_image=cover_image,
                track_number=f"{ci + 1}/{len(chapter_audio)}",
                album=title,
            )
            zf.writestr(filename, tagged)

        if progress_callback:
            progress_callback("encode", total_chapters, total_chapters, "Finalizing ZIP...")

    return zip_buf.getvalue()


def _parse_ffmpeg_progress(line: str) -> Optional[float]:
    import re
    m = re.search(r'out_time_ms=(\d+)', line)
    if m:
        return int(m.group(1)) / 1_000_000.0
    m = re.search(r'out_time=(\d+):(\d+):(\d+)\.(\d+)', line)
    if m:
        h, mn, s, frac_str = m.group(1), m.group(2), m.group(3), m.group(4)
        frac = int(frac_str) / (10 ** len(frac_str))
        return int(h) * 3600 + int(mn) * 60 + int(s) + frac
    m = re.search(r'time=(\d+):(\d+):(\d+)\.(\d+)', line)
    if m:
        h, mn, s, frac_str = m.group(1), m.group(2), m.group(3), m.group(4)
        frac = int(frac_str) / (10 ** len(frac_str))
        return int(h) * 3600 + int(mn) * 60 + int(s) + frac
    return None


# PCM format used when streaming to ffmpeg for M4B encoding.
# 44100 Hz mono s16le is universally supported and fine for audiobooks.
_M4B_SR = 44100
_M4B_CH = 1
_M4B_SW = 2  # bytes per sample (s16le)


def _blob_duration_ms(blob: bytes) -> int:
    """Return blob duration in milliseconds.
    Uses mutagen for a fast header-only read on MP3; falls back to a full pydub decode."""
    try:
        return int(MP3(io.BytesIO(blob)).info.length * 1000)
    except Exception:
        return len(AudioSegment.from_file(io.BytesIO(blob)))


def _decode_blob_to_pcm(blob: bytes) -> bytes:
    """Decode any audio blob to raw s16le PCM at the M4B target format."""
    seg = AudioSegment.from_file(io.BytesIO(blob))
    seg = seg.set_frame_rate(_M4B_SR).set_channels(_M4B_CH).set_sample_width(_M4B_SW)
    return seg.raw_data


def _silence_pcm_ms(duration_ms: int) -> bytes:
    """Return raw s16le silence of the requested duration."""
    num_samples = int(_M4B_SR * duration_ms / 1000)
    return bytes(num_samples * _M4B_CH * _M4B_SW)


def export_m4b(
    chapter_audio: List[Tuple[str, List[bytes]]],
    title: str,
    pause_ms: int = 500,
    author: Optional[str] = None,
    narrator: Optional[str] = None,
    genre: Optional[str] = None,
    year: Optional[str] = None,
    description: Optional[str] = None,
    cover_image: Optional[bytes] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> bytes:
    tmp_dir = tempfile.mkdtemp(prefix="m4b_export_")
    try:
        valid_chapters = [(t, b) for t, b in chapter_audio if b]
        if not valid_chapters:
            raise ValueError("No audio data to export")

        total_blobs = sum(len(blobs) for _, blobs in valid_chapters)

        # ------------------------------------------------------------------ #
        # Pass 1 – cheap duration scan (mutagen header reads, no full decode) #
        # Build chapter timestamps for ffmetadata before opening ffmpeg.       #
        # ------------------------------------------------------------------ #
        if progress_callback:
            progress_callback("decode", 0, total_blobs, "Calculating chapter timings...")

        chapter_meta = []
        cumulative_ms = 0
        for ch_idx, (ch_title, blobs) in enumerate(valid_chapters):
            chapter_start = cumulative_ms
            for i, blob in enumerate(blobs):
                cumulative_ms += _blob_duration_ms(blob)
                is_very_last = (ch_idx == len(valid_chapters) - 1) and (i == len(blobs) - 1)
                if not is_very_last:
                    cumulative_ms += pause_ms
            chapter_meta.append({
                "title": ch_title or f"Chapter {ch_idx + 1}",
                "start_ms": chapter_start,
                "end_ms": cumulative_ms,
            })

        total_duration_s = cumulative_ms / 1000.0

        # ------------------------------------------------------------------ #
        # Write ffmetadata                                                      #
        # ------------------------------------------------------------------ #
        def _esc_ffmeta(val: str) -> str:
            return val.replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\n", "\\\n")

        ffmetadata_path = os.path.join(tmp_dir, "chapters.txt")
        with open(ffmetadata_path, "w", encoding="utf-8") as f:
            f.write(";FFMETADATA1\n")
            if title:
                f.write(f"title={_esc_ffmeta(_safe_str(title))}\n")
            if author:
                f.write(f"artist={_esc_ffmeta(_safe_str(author))}\n")
            if narrator:
                f.write(f"album_artist={_esc_ffmeta(_safe_str(narrator))}\n")
            if genre:
                f.write(f"genre={_esc_ffmeta(_safe_str(genre))}\n")
            if year:
                f.write(f"date={_esc_ffmeta(_safe_str(year))}\n")
            if description:
                f.write(f"comment={_esc_ffmeta(_safe_str(description))}\n")
            f.write("\n")
            for ch in chapter_meta:
                f.write("[CHAPTER]\n")
                f.write("TIMEBASE=1/1000\n")
                f.write(f"START={ch['start_ms']}\n")
                f.write(f"END={ch['end_ms']}\n")
                f.write(f"title={_esc_ffmeta(_safe_str(ch['title']))}\n")
                f.write("\n")

        # ------------------------------------------------------------------ #
        # Launch ffmpeg – reads raw s16le PCM from stdin                       #
        # ------------------------------------------------------------------ #
        m4b_path = os.path.join(tmp_dir, "output.m4b")
        cmd = [
            "ffmpeg", "-y",
            "-f", "s16le", "-ar", str(_M4B_SR), "-ac", str(_M4B_CH),
            "-i", "pipe:0",
            "-i", ffmetadata_path,
            "-map_metadata", "1",
            "-map_chapters", "1",
            "-c:a", "aac",
            "-b:a", "128k",
            "-progress", "pipe:2",
            "-f", "mp4",
            m4b_path,
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
        )

        # Read ffmpeg's progress output on a background thread to avoid the
        # stdin-write / stderr-read deadlock that occurs in the main thread.
        stderr_lines: List[str] = []
        last_encode_pct = [0]

        def _read_stderr():
            for raw_line in proc.stderr:
                line = raw_line.decode("utf-8", errors="replace")
                stderr_lines.append(line)
                if progress_callback and total_duration_s > 0:
                    t = _parse_ffmpeg_progress(line)
                    if t is not None:
                        pct = min(int(t / total_duration_s * 100), 100)
                        if pct > last_encode_pct[0]:
                            last_encode_pct[0] = pct
                            progress_callback("encode", pct, 100, "Encoding audio...")

        stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
        stderr_thread.start()

        # ------------------------------------------------------------------ #
        # Pass 2 – stream PCM chunks directly into ffmpeg's stdin             #
        # Each chunk is decoded on-the-fly; only one blob lives in memory at  #
        # a time.  Silence is synthesised as zero bytes between chunks.       #
        # ------------------------------------------------------------------ #
        silence_pcm = _silence_pcm_ms(pause_ms)
        blob_count = 0
        try:
            for ch_idx, (_ch_title, blobs) in enumerate(valid_chapters):
                for i, blob in enumerate(blobs):
                    pcm = _decode_blob_to_pcm(blob)
                    proc.stdin.write(pcm)
                    blob_count += 1

                    is_very_last = (ch_idx == len(valid_chapters) - 1) and (i == len(blobs) - 1)
                    if not is_very_last:
                        proc.stdin.write(silence_pcm)

                    if progress_callback:
                        progress_callback(
                            "decode", blob_count, total_blobs,
                            f"Streaming chunk {blob_count} of {total_blobs}...",
                        )
        except BrokenPipeError:
            # ffmpeg died early – fall through to the returncode check below.
            logger.warning("ffmpeg stdin pipe broke during PCM stream; checking exit code")
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

        # Wait for ffmpeg to finish encoding the buffered data and close the file.
        stderr_thread.join(timeout=320)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError("ffmpeg timed out after PCM stream completed")

        if proc.returncode != 0:
            stderr_text = "".join(stderr_lines)
            logger.error(f"ffmpeg failed: {stderr_text}")
            raise RuntimeError(f"ffmpeg encoding failed: {stderr_text[-500:]}")

        # ------------------------------------------------------------------ #
        # Embed cover art and extra tags via mutagen (post-encode)             #
        # ------------------------------------------------------------------ #
        if cover_image:
            try:
                audio = MP4(m4b_path)
                img_format = MP4Cover.FORMAT_PNG if cover_image[:4] == b'\x89PNG' else MP4Cover.FORMAT_JPEG
                audio["covr"] = [MP4Cover(cover_image, imageformat=img_format)]
                if title:
                    audio["\xa9nam"] = [_safe_str(title)]
                if author:
                    audio["\xa9ART"] = [_safe_str(author)]
                if narrator:
                    audio["aART"] = [_safe_str(narrator)]
                if genre:
                    audio["\xa9gen"] = [_safe_str(genre)]
                if year:
                    audio["\xa9day"] = [_safe_str(year)]
                if description:
                    audio["\xa9cmt"] = [_safe_str(description)]
                audio.save()
            except Exception as e:
                logger.warning(f"Failed to embed cover art in M4B: {e}")

        with open(m4b_path, "rb") as f:
            return f.read()

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
