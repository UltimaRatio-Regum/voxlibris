---
title: narrate.ink StyleTTS2 Engine
emoji: 🎭
colorFrom: purple
colorTo: pink
sdk: docker
app_port: 7860
pinned: false
---

# narrate.ink StyleTTS2 TTS Engine

A HuggingFace Space that serves [StyleTTS2](https://github.com/yl4579/StyleTTS2) as a REST API for
text-to-speech with emotion control and voice cloning, implementing the
[narrate.ink TTS Engine API Contract](../../docs/tts-api-contract.md).

StyleTTS2 achieves human-level TTS synthesis through style diffusion and adversarial
training with large speech language models (SLMs). It uses a diffusion model to
generate the most suitable speaking style for the given text.

## Endpoints

### POST /GetEngineDetails

Returns engine capabilities including supported emotions and voice cloning support.

### POST /ConvertTextToSpeech

Converts text to speech with rich style control:
- **Emotion control**: neutral, happy, sad, angry, fear, excited, calm, surprised, whisper
- **Intensity**: Scales the embedding_scale to control how strongly the emotion affects output
- **Voice cloning**: Upload reference audio (base64 WAV) to clone voice timbre and prosody
- **Speed/pitch adjustment**: Via pyrubberband post-processing
- **Long-form support**: Automatically uses `long_inference` for longer texts with style continuity

### GET /health

Returns model loading status.

### GET /

Built-in test frontend with emotion selection, voice cloning upload, and parameter controls.

## How Emotion Control Works

StyleTTS2 doesn't use explicit emotion tags. Instead, it controls expressiveness through
diffusion parameters:

| Parameter | What it controls | Range |
|-----------|-----------------|-------|
| `alpha` | Timbre (0=reference voice, 1=text-predicted style) | 0.0 - 1.0 |
| `beta` | Prosody (0=reference voice, 1=text-predicted style) | 0.0 - 1.0 |
| `embedding_scale` | Expressiveness (higher=more emotional/dramatic) | 0.1 - 5.0 |
| `diffusion_steps` | Style diversity (more steps=more varied output) | 3 - 20 |

Each emotion preset maps to tuned combinations of these parameters. The intensity
slider scales `embedding_scale` to make the emotion more or less pronounced.

## Authentication

Set the `API_KEY` secret in your HuggingFace Space settings.
Requests must include `Authorization: Bearer <your-key>` header.
Leave `API_KEY` unset to disable authentication.

## Hardware Requirements

Requires GPU for reasonable inference speed. Recommended: T4 or better.
The LibriTTS multi-speaker model (~1.8 GB) downloads automatically on first startup.

## Deployment

1. Create a new HuggingFace Space with **Docker** SDK
2. Upload the contents of this folder
3. Select a GPU runtime (T4 recommended)
4. Set the `API_KEY` secret in Space settings (optional)
5. The model downloads automatically on first startup (~2 GB)
6. Register the Space URL in narrate.ink Settings under TTS Engine Management
