---
title: TomeVox Qwen3 TTS Engine
emoji: 🗣️
colorFrom: green
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# TomeVox Qwen3 TTS Engine

A HuggingFace Space that serves Qwen3-TTS as a REST API for text-to-speech,
implementing the [TomeVox TTS Engine API Contract](https://github.com/your-repo/docs/tts-api-contract.md).

Uses two Qwen3-TTS models:
- **Qwen3-TTS-12Hz-1.7B-CustomVoice** for built-in speaker generation with instruct-based emotion control
- **Qwen3-TTS-12Hz-1.7B-Base** for voice cloning via x-vector speaker embeddings

## Endpoints

### POST /GetEngineDetails

Returns engine capabilities, 9 built-in voices, supported emotions, and languages.

### POST /ConvertTextToSpeech

Converts text to speech. Supports:
- 9 built-in speakers (Ryan, Aiden, Vivian, Serena, Uncle Fu, Dylan, Eric, Ono Anna, Sohee)
- Instruct-based emotion control mapped from the TomeVox emotion set
- Voice cloning via base64-encoded WAV reference audio (x-vector mode)
- Speed adjustment via pyrubberband time-stretching
- Pitch adjustment via pyrubberband pitch-shifting
- Volume scaling

### GET /health

Returns model loading status for both CustomVoice and Base models.

### GET /

Built-in testing frontend with voice selection, cloning upload, and parameter controls.

## Authentication

Set the `API_KEY` secret in your HuggingFace Space settings.
Requests must include `Authorization: Bearer <your-key>` header.
Leave `API_KEY` unset to disable authentication.

## Built-in Voices

| ID | Name | Description | Native Language |
|----|------|-------------|-----------------|
| Vivian | Vivian | Bright, slightly edgy young female | Chinese |
| Serena | Serena | Warm, gentle young female | Chinese |
| Uncle_Fu | Uncle Fu | Seasoned male, low mellow timbre | Chinese |
| Dylan | Dylan | Youthful male, clear and natural | Chinese (Beijing) |
| Eric | Eric | Lively male, slightly husky brightness | Chinese (Sichuan) |
| Ryan | Ryan | Dynamic male, strong rhythmic drive | English |
| Aiden | Aiden | Sunny American male, clear midrange | English |
| Ono_Anna | Ono Anna | Playful female, light and nimble | Japanese |
| Sohee | Sohee | Warm female with rich emotion | Korean |

## Voice Cloning

Send a base64-encoded WAV file in the `voice_to_clone_sample` field.
Uses x-vector speaker embedding extraction (no transcript needed).
A 5-15 second clip of clear speech works best.

## Hardware Requirements

Loads two models (~3.4 GB total). A GPU with 8+ GB VRAM is recommended.
On HuggingFace Spaces, use an L4 or A10G instance.

## Deployment

1. Create a new HuggingFace Space with **Docker** SDK
2. Select a GPU runtime (L4 recommended)
3. Upload the contents of this folder
4. Set the `API_KEY` secret in Space settings (optional)
5. Models download automatically on first startup
6. Register the Space URL in TomeVox Settings under TTS Engine Management
