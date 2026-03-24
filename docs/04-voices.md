---
title: Voice Selection & Configuration
description: Choose and configure voices from multiple TTS engines
category: Audio
order: 4
keywords: [voices, TTS, engine, edge, soprano, voice library, custom, cloning]
---

# Voice Selection & Configuration

TomeVox supports multiple TTS engines, each offering different voices with unique characteristics. Understanding the available options helps you create more natural-sounding audiobooks.

## Built-in Engines

### Edge TTS (Microsoft Azure)
- **Voices:** Hundreds of neural voices across 80+ languages
- **Quality:** High-quality neural synthesis
- **Speed:** Fast generation via cloud API
- **Best for:** General-purpose narration, multilingual content

Edge TTS voices are identified with the `edge:` prefix (e.g., `edge:en-US-GuyNeural`).

### Soprano TTS
- **Voices:** Local model-based voices
- **Quality:** Good quality with very fast generation
- **Speed:** Ultra-fast (runs locally)
- **Best for:** Rapid prototyping, quick previews

## Voice Library

The Voice Library provides pre-recorded voice samples from the VCTK corpus. These samples can be used as reference voices for TTS engines that support voice cloning.

- Browse available voices with audio previews
- Filter by gender, accent, or characteristics
- Library voices use the `library:` prefix (e.g., `library:p232`)

Administrators can run AI analysis on Voice Library entries (via **Settings → Voice Library → Analyze**) to populate speaker metadata (name, gender, language, location, transcript) using the same LLM pipeline as custom voice analysis.

## Custom Voices

Upload your own voice recordings to create custom voices for cloning:

1. Go to **Settings** → **Custom Voices**
2. Click **Add Voice**
3. Upload a clean audio sample (WAV or MP3, 5-30 seconds recommended)
4. Provide a name and optional description
5. Optionally add a text transcript of the sample for better cloning

### AI Voice Analysis

After uploading a voice sample, you can run AI analysis to automatically extract metadata:

1. Select one or more custom voices in the **Custom Voices** list
2. Click **Analyze** — TomeVox sends the audio to a vision-capable LLM (via OpenRouter)
3. The AI returns:
   - **Suggested display name** — A descriptive name based on the voice characteristics
   - **Gender** — Male / Female / Androgynous
   - **Accent** — Primary language and region (e.g., "American English", "British RP")
   - **Summary** — A transcript or description of the sample content

This metadata is saved with the voice and shown in voice selection lists, making it easier to identify and search voices.

> **Requires** `AI_INTEGRATIONS_OPENROUTER_API_KEY` to be set. The model used can be overridden with the `VOICE_ANALYSIS_MODEL` environment variable (default: `google/gemini-2.5-flash`).

### Tips for Good Voice Samples

- Use clean, noise-free recordings
- Speak naturally at a consistent pace
- 10-20 seconds is ideal for most engines
- Avoid music or background sounds
- Record in a quiet environment

## Remote TTS Engines

You can connect external TTS services that implement the TomeVox TTS API contract:

- **XTTSv2** — Multilingual voice cloning
- **Qwen2.5/3-TTS** — Chinese/English neural TTS
- **OpenVoice V2** — Voice conversion and cloning
- **Chatterbox** — Expressive speech synthesis
- **StyleTTS2** — Style-transfer TTS
- **IndexTTS2** — Indexed voice TTS

See [Settings](./settings) for how to register and configure remote engines.

## Base Voice / Language Selection

Some TTS engines separate the concept of a "base voice" (which controls language and accent) from the cloned voice (which controls speaker identity). When available:

- Select a **base voice** for language/accent control
- Select a **cloning voice** for speaker identity
- The engine combines both for the final output

## Voice Assignment in Projects

### Single Voice
Assign one voice for the entire project. All text — narration and dialogue — uses the same voice.

### Per-Speaker Voices
Assign different voices for each detected speaker:

- **Narrator** — The default voice for non-dialogue text
- **Character voices** — Unique voices for each speaking character
- Characters are auto-detected during text analysis

You can change voice assignments at any time and regenerate audio for affected sections.

## Next Steps

- [Audio Generation](./audio-generation) — Start generating audio with your chosen voices
- [Emotion & Prosody](./emotion-prosody) — Fine-tune how emotions affect speech
- [Settings](./settings) — Configure TTS engines and defaults
