---
title: narrate.ink IndexTTS2 Engine
emoji: 🎙️
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# narrate.ink IndexTTS2 Engine

A HuggingFace Space that serves [IndexTTS2](https://github.com/index-tts/index-tts)
as a REST API, implementing the
[narrate.ink TTS Engine API Contract](https://github.com/your-repo/docs/tts-api-contract.md).

## Endpoints

### POST /GetEngineDetails

Returns engine capabilities, supported emotions, and voice cloning support.

### POST /ConvertTextToSpeech

Converts text to speech with zero-shot voice cloning. Requires a
`voice_to_clone_sample` (base64-encoded WAV). Supports 14 emotions mapped
to IndexTTS2's 8-dimensional emotion vector system.

### GET /health

Returns model loading status.

## Authentication

Set the `API_KEY` secret in your HuggingFace Space settings.
Requests must include `Authorization: Bearer <your-key>` header.
Leave `API_KEY` unset to disable authentication.

## Voice Cloning

IndexTTS2 is a zero-shot voice cloning engine — every request requires a
reference voice sample. Send a base64-encoded WAV file in the
`voice_to_clone_sample` field. A 6-15 second clear speech sample works best.

The engine disentangles speaker timbre from emotional expression, allowing
the cloned voice to speak with different emotions without affecting voice
identity.

## Emotion Support

IndexTTS2 uses an 8-dimensional emotion vector system (happy, angry, sad,
afraid, disgusted, melancholic, surprised, calm) with a fine-tuned Qwen3
model for emotion analysis. narrate.ink emotions are automatically mapped
to appropriate vector blends:

| Emotion     | Mapping Strategy                      |
|-------------|---------------------------------------|
| neutral     | High calm (0.8)                       |
| happy       | High happy (0.8)                      |
| sad         | High sad (0.8)                        |
| angry       | High angry (0.8)                      |
| fear        | High afraid (0.8)                     |
| disgust     | High disgusted (0.8)                  |
| surprise    | High surprised (0.7)                  |
| calm        | High calm (0.8)                       |
| excited     | Happy (0.6) + surprised (0.2)         |
| melancholy  | Sad (0.2) + melancholic (0.6)         |
| anxious     | Afraid (0.5) + slight calm (0.2)      |
| hopeful     | Happy (0.5) + calm (0.3)              |
| tender      | Happy (0.2) + calm (0.5)              |
| proud       | Happy (0.5) + surprised (0.1)         |

The `intensity` parameter (1-100) scales the emotion vectors. Additional
prosody reinforcement is applied via pyrubberband speed/pitch adjustments.

## Key Features

- **Emotion-Speaker Disentanglement**: Independent control over voice timbre
  (from reference audio) and emotional expression (from emotion vectors)
- **Zero-Shot Voice Cloning**: Clone any voice from a short reference audio
- **Duration Control**: Supports both free generation and explicit token-count
  modes for precise audio length
- **Multilingual**: Chinese and English (with more languages supported)
- **Built-in Qwen3 Emotion Model**: Fine-tuned for text-to-emotion analysis

## Limits

- Maximum 500 characters per request (longer text is truncated at word boundary)
- Output: 22050 Hz mono 16-bit WAV
- Reference audio: max 15 seconds (longer clips are auto-truncated)

## Environment Variables

| Variable    | Description                            | Default         |
|-------------|----------------------------------------|-----------------|
| `API_KEY`   | Bearer token for authentication        | (none/disabled) |
| `MODEL_DIR` | Path to model checkpoints directory    | `checkpoints`   |
| `USE_FP16`  | Enable half-precision inference        | `true`          |

## Deployment

1. Create a new HuggingFace Space with **Docker** SDK
2. Upload the contents of this folder
3. Set the `API_KEY` secret in Space settings (optional)
4. The model downloads automatically during build (~5 GB)
5. Requires GPU (A10G or better recommended for reasonable speed)
6. Register the Space URL in narrate.ink Settings under TTS Engine Management
