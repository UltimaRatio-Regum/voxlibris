---
title: narrate.ink Qwen3 TTS Engine
emoji: 🗣️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# narrate.ink Qwen 2.5 Omni TTS Engine

A HuggingFace Space that serves the Qwen2.5-Omni-7B model as a REST API for
text-to-speech, implementing the
[narrate.ink TTS Engine API Contract](https://github.com/your-repo/docs/tts-api-contract.md).

## Endpoints

### POST /GetEngineDetails

Returns engine capabilities, built-in voices, supported emotions, and languages.

### POST /ConvertTextToSpeech

Converts text to speech. Supports:
- Built-in voices (Chelsie, Ethan)
- Voice cloning via base64-encoded WAV samples
- Emotion prompting with intensity control
- Speed adjustment via pyrubberband time-stretching
- Pitch adjustment via pyrubberband pitch-shifting
- Volume scaling

### GET /health

Returns model loading status.

## Authentication

Set the `API_KEY` secret in your HuggingFace Space settings.
Requests must include `Authorization: Bearer <your-key>` header.
Leave `API_KEY` unset to disable authentication.

## Built-in Voices

| ID | Name | Description |
|----|------|-------------|
| Chelsie | Chelsie | Default female voice, warm and clear |
| Ethan | Ethan | Male voice, confident and steady |

## Voice Cloning

Qwen2.5-Omni supports voice cloning by conditioning on a reference audio sample.
Send a base64-encoded WAV file in the `voice_to_clone_sample` field. A 5-15
second clear speech sample works best.

## Supported Languages

en, zh, ja, ko, fr, de, es, it, pt, ru, ar, nl, pl, tr, vi, th

## Hardware Requirements

This model is ~14 GB. A GPU with at least 16 GB VRAM is recommended.
On HuggingFace Spaces, use an A10G or A100 instance.

## Deployment

1. Create a new HuggingFace Space with **Docker** SDK
2. Select a GPU runtime (A10G Small recommended)
3. Upload the contents of this folder
4. Set the `API_KEY` secret in Space settings (optional)
5. The model downloads automatically on first startup (~14 GB)
6. Register the Space URL in narrate.ink Settings under TTS Engine Management
