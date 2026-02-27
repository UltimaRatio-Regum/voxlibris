---
title: VoxLibris XTTSv2 Engine
emoji: 🔊
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# VoxLibris XTTSv2 TTS Engine

A HuggingFace Space that serves the Coqui XTTSv2 model as a REST API,
implementing the [VoxLibris TTS Engine API Contract](https://github.com/your-repo/docs/tts-api-contract.md).

## Endpoints

### POST /GetEngineDetails

Returns engine capabilities, supported emotions, and available languages.

### POST /ConvertTextToSpeech

Converts text to speech. Supports voice cloning via base64-encoded WAV samples.

### GET /health

Returns model loading status.

## Authentication

Set the `API_KEY` secret in your HuggingFace Space settings.
Requests must include `Authorization: Bearer <your-key>` header.
Leave `API_KEY` unset to disable authentication.

## Voice Cloning

XTTSv2 supports voice cloning. Send a base64-encoded WAV file in the
`voice_to_clone_sample` field of the ConvertTextToSpeech request.
A 6-15 second clear speech sample works best.

## Supported Languages

en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, ja, hu, ko

## Deployment

1. Create a new HuggingFace Space with **Docker** SDK
2. Upload the contents of this folder
3. Set the `API_KEY` secret in Space settings (optional)
4. The model downloads automatically on first startup (~1.8 GB)
5. Register the Space URL in VoxLibris Settings under TTS Engine Management
