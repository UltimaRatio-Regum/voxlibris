---
title: TomeVox OpenVoice V2 Engine
emoji: 🎙️
colorFrom: yellow
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# TomeVox OpenVoice V2 TTS Engine

A HuggingFace Space that serves MyShell's OpenVoice V2 as a REST API for
text-to-speech with instant voice cloning, implementing the
[TomeVox TTS Engine API Contract](../../docs/tts-api-contract.md).

OpenVoice V2 uses a two-stage architecture:
1. **MeloTTS** generates high-quality base speech in the selected language/voice
2. **ToneColorConverter** transfers the voice characteristics from a reference audio to the generated speech

## Endpoints

### POST /GetEngineDetails

Returns engine capabilities, 10 built-in voices across 6 languages, and cloning support.

### POST /ConvertTextToSpeech

Converts text to speech. Supports:
- 10 built-in voices across 6 languages (English variants, Spanish, French, Chinese, Japanese, Korean)
- Instant voice cloning via tone color conversion (base64-encoded WAV reference)
- Speed adjustment via MeloTTS native speed parameter
- Pitch adjustment via pyrubberband pitch-shifting
- Volume scaling

### GET /health

Returns model loading status for ToneColorConverter and all MeloTTS language models.

### GET /

Built-in testing frontend with voice selection, cloning upload, and parameter controls.

## Authentication

Set the `API_KEY` secret in your HuggingFace Space settings.
Requests must include `Authorization: Bearer <your-key>` header.
Leave `API_KEY` unset to disable authentication.

## Built-in Voices

| ID | Name | Language |
|----|------|----------|
| en-default | English Default | English (Newest) |
| en-us | English (US) | English |
| en-br | English (British) | English |
| en-au | English (Australian) | English |
| en-india | English (Indian) | English |
| es-default | Spanish | Spanish |
| fr-default | French | French |
| zh-default | Chinese | Chinese |
| jp-default | Japanese | Japanese |
| kr-default | Korean | Korean |

## Voice Cloning

OpenVoice V2 performs instant voice cloning using tone color conversion:
1. MeloTTS generates speech in the selected base voice
2. ToneColorConverter extracts speaker embeddings from your reference audio
3. The base speech is transformed to match the reference voice's timbre

Send a base64-encoded WAV or MP3 file in the `voice_to_clone_sample` field.
A 5-15 second clip of clear speech works best. You also select a base voice
to control the language and pronunciation style.

## Hardware Requirements

Lightweight models (~500 MB total). Runs on CPU but benefits from GPU acceleration.
On HuggingFace Spaces, a free CPU instance works, but GPU (T4) is recommended for speed.

## Deployment

1. Create a new HuggingFace Space with **Docker** SDK
2. Upload the contents of this folder
3. Set the `API_KEY` secret in Space settings (optional)
4. Checkpoints download automatically during Docker build (~200 MB)
5. MeloTTS models download on first startup from HuggingFace
6. Register the Space URL in TomeVox Settings under TTS Engine Management
