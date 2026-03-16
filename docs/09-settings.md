---
title: Settings
description: Configure TTS engines, voices, parsing prompts, and preferences
category: Configuration
order: 9
keywords: [settings, configuration, TTS engine, parsing prompt, emotion weights, default voice]
---

# Settings

The Settings tab lets you configure VoxLibris to match your workflow and preferences.

## Default TTS Settings

### Default Engine
Select which TTS engine to use by default for new projects:
- **Edge TTS** — Cloud-based Microsoft Azure neural voices
- **Soprano** — Ultra-fast local generation
- Any registered remote engine

### Default Voice
Set the default voice used for new projects. This is used for the narrator and as the initial voice for all speakers.

## Custom Voices

Manage your personal voice library for voice cloning:

- **Add Voice** — Upload a WAV or MP3 sample
- **Edit** — Update the name, description, or voice text transcript
- **Delete** — Remove a custom voice
- **Preview** — Listen to your voice sample

### Voice Text
Some engines produce better cloning results when you provide a text transcript of your voice sample. The engine uses this to better understand the speech patterns in your sample.

## Remote TTS Engines

Register and manage external TTS services:

### Adding a Remote Engine
1. Click **Add Engine**
2. Enter the engine **name** and **endpoint URL**
3. The system will attempt to connect and verify the engine
4. Once verified, the engine appears in voice selection

### Engine Properties
| Property | Description |
|----------|-------------|
| **Name** | Display name for the engine |
| **Endpoint URL** | The REST API URL of the engine |
| **Shared** | Whether all users can access this engine (admin toggle) |
| **Status** | Connection status (online, warming up, offline) |

### Warm-up Behavior
Some remote engines (especially on HuggingFace Spaces) need to warm up from a cold start:
- The system automatically polls the engine during warm-up
- A progress indicator shows the warm-up status
- You can cancel the warm-up if needed
- Once warm, the engine stays available until it goes to sleep

## Parsing Prompt

The LLM prompt used for text chunking and speaker identification is fully editable:

1. Go to **Settings** → **Parsing Prompt**
2. View or edit the system prompt
3. Save your changes

### Why Edit the Prompt?
- Improve speaker detection for specific content types
- Add rules for unusual dialogue formats
- Customize chunk size preferences
- Handle domain-specific terminology

### Reset
You can reset the prompt to the built-in default at any time.

## Emotion Prosody Weights

Configure how strongly each of the 14 emotions affects speech generation:

- Adjust the slider for each emotion
- Higher values = more expressive speech
- Lower values = more subtle expression
- See [Emotion & Prosody](./emotion-prosody) for details

## LLM Model Selection

Choose which language model to use for text analysis:
- Multiple models are available via OpenRouter
- Different models offer varying quality/speed tradeoffs
- The default model is pre-selected for optimal results

## Next Steps

- [Voice Selection](./voices) — Use your configured voices in projects
- [Emotion & Prosody](./emotion-prosody) — Fine-tune emotional expression
- [Admin](./admin) — User and system management (administrators only)
