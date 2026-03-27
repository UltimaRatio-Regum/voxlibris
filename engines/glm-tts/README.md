---
title: narrate.ink GLM-TTS Engine
emoji: 🎙️
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# narrate.ink GLM-TTS Engine

A HuggingFace Space that serves [GLM-TTS](https://github.com/zai-org/GLM-TTS)
as a REST API, implementing the
[narrate.ink TTS Engine API Contract](https://github.com/your-repo/docs/tts-api-contract.md).

GLM-TTS is a zero-shot bilingual (Chinese/English) TTS model by Zhipu AI, capable
of cloning a speaker's voice from a short reference sample.

## Endpoints

### POST /GetEngineDetails

Returns engine capabilities, supported emotions, and available languages.

### POST /ConvertTextToSpeech

Converts text to speech using zero-shot voice cloning. Requires a
`voice_to_clone_sample` (base64-encoded WAV). Supports emotion-driven prosody
adjustments via speed and pitch post-processing.

### GET /health

Returns model loading status and active compute device (CPU/CUDA).

## Authentication

Set the `API_KEY` secret in your HuggingFace Space settings.
Requests must include `Authorization: Bearer <your-key>` header.
Leave `API_KEY` unset to disable authentication.

## Voice Cloning

GLM-TTS is a zero-shot voice cloning engine — every request **requires** a
reference voice sample. Send a base64-encoded WAV file in the
`voice_to_clone_sample` field. A 6-15 second clear speech sample works best.

## Emotion Support

Emotions are emulated through post-processing speed and pitch shifts applied
to the generated audio via pyrubberband:

| Emotion    | Speed  | Pitch  |
|------------|--------|--------|
| neutral    | 1.00×  |  0.0 st |
| happy      | 1.04×  | +0.6 st |
| sad        | 0.93×  | -0.4 st |
| angry      | 1.06×  | -0.3 st |
| fear       | 1.05×  | +0.4 st |
| surprise   | 1.07×  | +0.7 st |
| disgust    | 0.97×  | -0.3 st |
| excited    | 1.06×  | +0.8 st |
| calm       | 0.94×  | -0.2 st |
| confused   | 0.97×  | +0.2 st |
| anxious    | 1.04×  | +0.4 st |
| hopeful    | 1.02×  | +0.4 st |
| melancholy | 0.92×  | -0.5 st |

The `intensity` parameter (1-100) scales the emotion effect; 50 is the neutral baseline.

## Supported Languages

- `zh` — Mandarin Chinese
- `en` — English
- `zh-en` — Mixed Chinese/English (code-switching)

## Limits

- Maximum 500 characters per request (longer text is truncated at word boundary)
- Output: 24 kHz mono 16-bit WAV

## Deployment

1. Create a new HuggingFace Space with **Docker** SDK
2. Upload the contents of this folder
3. Set the `API_KEY` secret in Space settings (optional)
4. The model (~several GB) downloads automatically from `zai-org/GLM-TTS` on first startup
5. **A GPU is required** — the upstream inference code calls `.cuda()` unconditionally (T4 minimum)
6. Register the Space URL in narrate.ink Settings under TTS Engine Management
