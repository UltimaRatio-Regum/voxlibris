---
title: Settings
description: Configure TTS engines, voices, parsing prompts, and preferences
category: Configuration
order: 9
keywords: [settings, configuration, TTS engine, parsing prompt, emotion weights, default voice]
---

# Settings

The Settings tab lets you configure narrate.ink to match your workflow and preferences.

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
- **Analyze** — Run AI analysis to automatically extract display name, gender, accent, and a transcript summary (requires OpenRouter API key)
- **Edit** — Update the name, description, or voice text transcript
- **Delete** — Remove a custom voice
- **Preview** — Listen to your voice sample

### Voice Text
Some engines produce better cloning results when you provide a text transcript of your voice sample. The engine uses this to better understand the speech patterns in your sample.

### Voice Analysis
The **Analyze** button sends selected voice samples to a vision-capable LLM and writes back structured metadata. See [Voice Selection](./voices) for details on what is extracted and how to get the best results.

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

### Engine-Specific Parameters

When an engine is registered, narrate.ink reads its `engine_params` declaration from `GetEngineDetails` and presents those parameters as UI controls in generation settings and the chunk editor. For example, Chatterbox exposes:

| Parameter | Range | Description |
|-----------|-------|-------------|
| **Exaggeration** | 0.25 – 2.0 | Controls how dramatically emotions are expressed |
| **CFG Weight** | 0.0 – 1.0 | Classifier-free guidance strength |
| **Temperature** | 0.05 – 5.0 | Sampling randomness |

Engine-specific parameters override the automatic emotion-to-parameter mapping when set explicitly. Each engine defines its own set; parameters are discovered automatically and require no configuration in narrate.ink.

### Engine Concurrency

Control how many jobs each engine can run in parallel via **Settings → Engine Concurrency**. Lowering this prevents a single engine from being overwhelmed by simultaneous requests; increasing it can improve throughput when you have multiple GPU workers behind one endpoint.

### Warm-up Behavior
Some remote engines (especially on HuggingFace Spaces) need to warm up from a cold start:
- The system automatically polls the engine every 5 seconds during warm-up
- Each poll has a 5-second timeout, giving ~10 seconds between attempts when the engine is unresponsive
- Warm-up will wait up to **10 minutes** (600 seconds) before marking the engine as unavailable
- A progress indicator shows the warm-up status in the Jobs view
- You can cancel the warm-up if needed
- Once warm, the engine stays available until it goes to sleep again

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
