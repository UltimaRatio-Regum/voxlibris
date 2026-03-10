---
title: VoxLibris Chatterbox TTS Engine
emoji: 🗣️
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# VoxLibris Chatterbox TTS Engine

A HuggingFace Space that serves [Chatterbox TTS](https://github.com/resemble-ai/chatterbox)
as a REST API, implementing the
[VoxLibris TTS Engine API Contract](https://github.com/your-repo/docs/tts-api-contract.md).

## Endpoints

### POST /GetEngineDetails

Returns engine capabilities, supported emotions, and voice cloning support.

### POST /ConvertTextToSpeech

Converts text to speech with voice cloning. Requires a `voice_to_clone_sample`
(base64-encoded WAV). Supports emotion-driven expressiveness via the exaggeration
parameter, mapped automatically from VoxLibris emotions.

### GET /health

Returns model loading status.

## Authentication

Set the `API_KEY` secret in your HuggingFace Space settings.
Requests must include `Authorization: Bearer <your-key>` header.
Leave `API_KEY` unset to disable authentication.

## Voice Cloning

Chatterbox is a voice-cloning TTS engine — every request requires a reference
voice sample. Send a base64-encoded WAV file in the `voice_to_clone_sample`
field. A 6-15 second clear speech sample works best.

## Emotion Support

Chatterbox controls expressiveness through its `exaggeration` parameter (0.0-1.0).
The engine automatically maps VoxLibris emotions to appropriate exaggeration levels:

| Emotion   | Exaggeration | Description               |
|-----------|-------------|---------------------------|
| neutral   | 0.50        | Normal, conversational    |
| calm      | 0.40        | Subdued, relaxed          |
| happy     | 0.70        | Cheerful, upbeat          |
| sad       | 0.60        | Somber, downcast          |
| angry     | 0.85        | Intense, forceful         |
| fear      | 0.75        | Tense, urgent             |
| excited   | 0.90        | High energy, enthusiastic |
| surprise  | 0.80        | Startled, astonished      |

The `intensity` parameter (1-100) scales the exaggeration further.

## Limits

- Maximum 300 characters per request (longer text is truncated at word boundary)
- Output: 24kHz mono 16-bit WAV

## Deployment

1. Create a new HuggingFace Space with **Docker** SDK
2. Upload the contents of this folder
3. Set the `API_KEY` secret in Space settings (optional)
4. The model downloads automatically on first startup (~500 MB)
5. Requires GPU (T4 minimum recommended)
6. Register the Space URL in VoxLibris Settings under TTS Engine Management
