#!/usr/bin/env python3
"""
Voice Library Initialization Script

Loads all voice samples from voice_samples/ directory into the PostgreSQL
voice_library table. Parses metadata from filenames and reads audio/transcript files.

Filename pattern: p{num}_{gender}_{age}_{language}_{location}.txt
Audio files: p{num}_mic1.wav, p{num}_mic2.wav

Usage:
    python scripts/init_voice_library.py
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from database import init_database, get_db_session, VoiceLibraryEntry

VOICE_SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "voice_samples")


def format_location(location: str, language: str) -> str:
    formatted = location.replace("_", " ")
    lang_lower = language.lower()

    suffixes = {
        "scottish": ("scotland", ", Scotland"),
        "northernirish": ("ireland", ", Northern Ireland"),
        "irish": ("ireland", ", Ireland"),
        "welsh": ("wales", ", Wales"),
        "english": ("england", ", England"),
        "american": ("america", ", USA"),
        "canadian": ("canada", ", Canada"),
        "australian": ("australia", ", Australia"),
        "newzealand": ("zealand", ", New Zealand"),
        "southafrican": ("africa", ", South Africa"),
        "indian": ("india", ", India"),
    }

    if lang_lower in suffixes:
        check, suffix = suffixes[lang_lower]
        if check not in formatted.lower():
            formatted += suffix

    return formatted


def load_voice_samples():
    if not os.path.exists(VOICE_SAMPLES_DIR):
        print(f"Voice samples directory not found: {VOICE_SAMPLES_DIR}")
        return

    init_database()
    db = get_db_session()

    metadata_pattern = re.compile(r"p(\d+)_([MF])_(\d+)_([^_]+)_(.+?)(?:_nopunct)?\.txt")
    seen_ids = set()
    loaded = 0
    skipped = 0

    for txt_file in sorted(os.listdir(VOICE_SAMPLES_DIR)):
        if "_nopunct" in txt_file or not txt_file.endswith(".txt"):
            continue

        match = metadata_pattern.match(txt_file)
        if not match:
            continue

        voice_num = match.group(1)
        voice_id = f"p{voice_num}"

        if voice_id in seen_ids:
            continue
        seen_ids.add(voice_id)

        existing = db.query(VoiceLibraryEntry).filter(VoiceLibraryEntry.id == voice_id).first()
        if existing:
            skipped += 1
            continue

        gender = match.group(2)
        age = int(match.group(3))
        language = match.group(4)
        location = match.group(5)

        mic1_path = os.path.join(VOICE_SAMPLES_DIR, f"{voice_id}_mic1.wav")
        mic2_path = os.path.join(VOICE_SAMPLES_DIR, f"{voice_id}_mic2.wav")

        if not os.path.exists(mic1_path):
            print(f"  Skipping {voice_id}: mic1.wav not found")
            continue

        try:
            transcript_path = os.path.join(VOICE_SAMPLES_DIR, txt_file)
            transcript = open(transcript_path, "r").read().strip()
        except Exception:
            transcript = None

        try:
            with open(mic1_path, "rb") as f:
                audio_data = f.read()
        except Exception as e:
            print(f"  Skipping {voice_id}: failed to read mic1.wav: {e}")
            continue

        alt_audio_data = None
        if os.path.exists(mic2_path):
            try:
                with open(mic2_path, "rb") as f:
                    alt_audio_data = f.read()
            except Exception:
                pass

        duration = 0.0
        try:
            import wave
            with wave.open(mic1_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration = frames / float(rate) if rate > 0 else 0.0
        except Exception:
            pass

        display_location = format_location(location, language)
        display_name = f"Voice {voice_num}: {gender}/{age} {display_location}"

        entry = VoiceLibraryEntry(
            id=voice_id,
            name=display_name,
            gender=gender,
            age=age,
            language=language,
            location=location,
            transcript=transcript,
            duration=duration,
            audio_data=audio_data,
            alt_audio_data=alt_audio_data,
        )
        db.add(entry)
        loaded += 1

        if loaded % 10 == 0:
            db.commit()
            print(f"  Loaded {loaded} voices...")

    db.commit()
    db.close()

    print(f"\nDone! Loaded {loaded} new voices, skipped {skipped} existing.")
    print(f"Total unique voice IDs found: {len(seen_ids)}")


if __name__ == "__main__":
    print("VoxLibris Voice Library Initialization")
    print(f"Source: {VOICE_SAMPLES_DIR}")
    print()
    load_voice_samples()
