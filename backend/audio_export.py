"""
Audio export module for generating downloadable audiobook files.
Supports: single MP3, MP3 per chapter (ZIP), and M4B (AAC with chapters).
"""
import io
import os
import struct
import subprocess
import tempfile
import zipfile
import logging
from typing import List, Optional, Tuple

from pydub import AudioSegment
from mutagen.mp3 import MP3
from mutagen.id3 import (
    ID3, TIT2, TPE1, TPE2, TALB, TCON, TDRC, COMM, TRCK, APIC
)
from mutagen.mp4 import MP4, MP4Cover

logger = logging.getLogger(__name__)


def _build_mp3_segment(audio_blobs: List[bytes], pause_ms: int = 500) -> AudioSegment:
    combined = AudioSegment.empty()
    silence = AudioSegment.silent(duration=pause_ms) if pause_ms > 0 else None

    for i, blob in enumerate(audio_blobs):
        try:
            seg = AudioSegment.from_file(io.BytesIO(blob))
            if i > 0 and silence:
                combined += silence
            combined += seg
        except Exception as e:
            logger.warning(f"Skipping invalid audio blob (index {i}): {e}")

    return combined


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
    tags.add(TIT2(encoding=3, text=title))
    if album:
        tags.add(TALB(encoding=3, text=album))
    if author:
        tags.add(TPE1(encoding=3, text=author))
    if narrator:
        tags.add(TPE2(encoding=3, text=narrator))
    if genre:
        tags.add(TCON(encoding=3, text=genre))
    if year:
        tags.add(TDRC(encoding=3, text=year))
    if description:
        tags.add(COMM(encoding=3, lang="eng", desc="", text=description))
    if track_number:
        tags.add(TRCK(encoding=3, text=track_number))
    if cover_image:
        mime = "image/jpeg"
        if cover_image[:4] == b'\x89PNG':
            mime = "image/png"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover_image))

    out = io.BytesIO()
    audio.save(out)
    return out.getvalue()


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
) -> bytes:
    all_blobs = []
    for _ch_title, blobs in chapter_audio:
        all_blobs.extend(blobs)

    combined = _build_mp3_segment(all_blobs, pause_ms)
    buf = io.BytesIO()
    combined.export(buf, format="mp3", bitrate="192k")
    mp3_bytes = buf.getvalue()

    return _apply_id3_tags(
        mp3_bytes, title=title, author=author, narrator=narrator,
        genre=genre, year=year, description=description,
        cover_image=cover_image, album=title,
    )


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
) -> bytes:
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, (ch_title, blobs) in enumerate(chapter_audio):
            if not blobs:
                continue

            combined = _build_mp3_segment(blobs, pause_ms)
            mp3_buf = io.BytesIO()
            combined.export(mp3_buf, format="mp3", bitrate="192k")

            safe_title = ch_title or f"Chapter {i + 1}"
            safe_title = "".join(c for c in safe_title if c.isalnum() or c in " _-").strip()
            filename = f"{i + 1:02d} - {safe_title}.mp3"

            tagged = _apply_id3_tags(
                mp3_buf.getvalue(),
                title=safe_title,
                author=author,
                narrator=narrator,
                genre=genre,
                year=year,
                description=description,
                cover_image=cover_image,
                track_number=f"{i + 1}/{len(chapter_audio)}",
                album=title,
            )
            zf.writestr(filename, tagged)

    return zip_buf.getvalue()


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
) -> bytes:
    tmp_dir = tempfile.mkdtemp(prefix="m4b_export_")
    try:
        chapter_files = []
        chapter_meta = []
        cumulative_ms = 0

        for i, (ch_title, blobs) in enumerate(chapter_audio):
            if not blobs:
                continue

            combined = _build_mp3_segment(blobs, pause_ms)
            wav_path = os.path.join(tmp_dir, f"ch_{i:03d}.wav")
            combined.export(wav_path, format="wav")

            duration_ms = len(combined)
            chapter_meta.append({
                "title": ch_title or f"Chapter {i + 1}",
                "start_ms": cumulative_ms,
                "end_ms": cumulative_ms + duration_ms,
            })
            cumulative_ms += duration_ms
            chapter_files.append(wav_path)

        if not chapter_files:
            raise ValueError("No audio data to export")

        concat_wav = os.path.join(tmp_dir, "full.wav")
        if len(chapter_files) == 1:
            os.rename(chapter_files[0], concat_wav)
        else:
            full = AudioSegment.empty()
            for wf in chapter_files:
                full += AudioSegment.from_wav(wf)
            full.export(concat_wav, format="wav")

        m4b_path = os.path.join(tmp_dir, "output.m4b")

        def _esc_ffmeta(val: str) -> str:
            return val.replace("\\", "\\\\").replace("=", "\\=").replace(";", "\\;").replace("#", "\\#").replace("\n", "\\\n")

        ffmetadata_path = os.path.join(tmp_dir, "chapters.txt")
        with open(ffmetadata_path, "w") as f:
            f.write(";FFMETADATA1\n")
            if title:
                f.write(f"title={_esc_ffmeta(title)}\n")
            if author:
                f.write(f"artist={_esc_ffmeta(author)}\n")
            if narrator:
                f.write(f"album_artist={_esc_ffmeta(narrator)}\n")
            if genre:
                f.write(f"genre={_esc_ffmeta(genre)}\n")
            if year:
                f.write(f"date={_esc_ffmeta(year)}\n")
            if description:
                f.write(f"comment={_esc_ffmeta(description)}\n")
            f.write("\n")

            for ch in chapter_meta:
                f.write("[CHAPTER]\n")
                f.write("TIMEBASE=1/1000\n")
                f.write(f"START={ch['start_ms']}\n")
                f.write(f"END={ch['end_ms']}\n")
                f.write(f"title={_esc_ffmeta(ch['title'])}\n")
                f.write("\n")

        cmd = [
            "ffmpeg", "-y",
            "-i", concat_wav,
            "-i", ffmetadata_path,
            "-map_metadata", "1",
            "-map_chapters", "1",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "mp4",
            m4b_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.error(f"ffmpeg failed: {result.stderr}")
            raise RuntimeError(f"ffmpeg encoding failed: {result.stderr[-500:]}")

        if cover_image:
            try:
                audio = MP4(m4b_path)
                mime = "image/jpeg"
                img_format = MP4Cover.FORMAT_JPEG
                if cover_image[:4] == b'\x89PNG':
                    mime = "image/png"
                    img_format = MP4Cover.FORMAT_PNG
                audio["covr"] = [MP4Cover(cover_image, imageformat=img_format)]
                if title:
                    audio["\xa9nam"] = [title]
                if author:
                    audio["\xa9ART"] = [author]
                if narrator:
                    audio["aART"] = [narrator]
                if genre:
                    audio["\xa9gen"] = [genre]
                if year:
                    audio["\xa9day"] = [year]
                if description:
                    audio["\xa9cmt"] = [description]
                audio.save()
            except Exception as e:
                logger.warning(f"Failed to embed cover art in M4B: {e}")

        with open(m4b_path, "rb") as f:
            return f.read()

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
