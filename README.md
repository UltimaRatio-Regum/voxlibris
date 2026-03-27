<p align="center">
  <img src="docs/images/narrate.ink-logo.png" alt="narrate.ink" width="80" />
</p>

<h1 align="center">narrate.ink</h1>

<p align="center">
  <strong>Self-hosted AI audiobook creator — turn ebooks into expressive, multi-voice audiobooks</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#screenshots">Screenshots</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#supported-tts-engines">TTS Engines</a> •
  <a href="#how-it-works">How It Works</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#tts-engine-api">Engine API</a> •
  <a href="#cost-comparison">Cost Comparison</a> •
  <a href="#docs">Docs</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License" />
  <img src="https://img.shields.io/badge/python-3.11+-brightgreen.svg" alt="Python" />
  <img src="https://img.shields.io/badge/self--hosted-yes-orange.svg" alt="Self-hosted" />
</p>

---

narrate.ink transforms plain text and EPUB files into full-length, multi-voice audiobooks with automatic speaker detection, emotion analysis, and chapter-aware M4B export. It runs entirely on your own infrastructure — no per-character fees, no cloud lock-in, no usage caps.

Upload an ebook, and narrate.ink will:

1. **Parse and segment** the text into chapters, sections, and audio-sized chunks
2. **Detect speakers** — identify dialogue, attribute it to characters, and separate narration
3. **Assign emotions** — label each chunk with one of 14 emotions (happy, tense, angry, tender, etc.)
4. **Generate audio** — render speech using any connected TTS engine with per-character voices
5. **Export** — produce M4B audiobooks with embedded chapter markers, or MP3/ZIP

## Features

- **EPUB & text import** — Upload `.epub` files with automatic chapter extraction, or paste/upload plain text
- **AI-powered speaker detection** — Five detection strategies: explicit dialogue tags, compound name handling, pronoun resolution, narrative context, and turn-taking inference
- **14-emotion analysis** — Each chunk is labeled with an emotion (neutral, happy, sad, angry, fearful, surprised, tender, excited, tense, amused, calm, bored, contemptuous, disgusted) that shapes how the TTS engine renders it
- **Multi-voice output** — Assign different voices to the narrator and each detected character
- **Engine-agnostic architecture** — Plug in any TTS engine that implements two REST endpoints. Swap between Chatterbox, XTTSv2, StyleTTS2, Edge TTS, and more without touching application code
- **Voice cloning** — Upload a short audio sample and clone it as a character voice (engine-dependent)
- **AI voice analysis** — Automatically extract display name, gender, accent, and a speech transcript from any custom voice sample or VCTK library entry using a vision-capable LLM
- **Engine-specific parameters** — Engines declare their own tunable controls (e.g., Chatterbox exposes Exaggeration, CFG Weight, Temperature). narrate.ink auto-discovers them on registration and presents them as UI controls
- **Hierarchical project editor** — Book → Chapter → Section → Chunk tree with cascading settings overrides at every level
- **Per-chunk control** — Override speaker, emotion, voice, speed, pitch, and engine for any individual chunk and regenerate just that segment
- **Emotion prosody weights** — Fine-tune how each emotion maps to pitch, speed, volume, and intensity adjustments per engine
- **Customizable parsing prompt** — Edit the LLM system prompt used for text chunking and speaker identification to handle unusual formats
- **Background job queue** — Generation runs asynchronously with real-time progress tracking; listen to completed chunks while the rest generate
- **Export formats** — Single MP3, MP3-per-chapter ZIP, or M4B with embedded chapter markers and metadata
- **Multi-user with data isolation** — User accounts with private projects, voices, and jobs; shared or private TTS engines; invite-only or open registration
- **Built-in docs** — In-app documentation accessible from the header

## Screenshots

| | |
|:---:|:---:|
| ![Project Wizard](docs/screenshots/project-wizard.png) | ![Projects List](docs/screenshots/projects-list.png) |
| **Project Wizard** — Upload an ebook or paste text, choose a TTS engine and analysis model | **Projects List** — Browse all your audiobook projects with chapter/chunk counts and status |
| ![Project Editor](docs/screenshots/project-editor.png) | ![Chunk Detail](docs/screenshots/chunk-detail.png) |
| **Project Editor** — Two-panel layout with the full Book → Chapter → Section → Chunk tree and per-speaker voice assignment | **Chunk Detail** — View a chunk's text, auto-detected speaker and emotion, override either, regenerate audio, or combine with adjacent chunks |
| ![Chapter View](docs/screenshots/chapter-view.png) | ![Audiobook Metadata](docs/screenshots/audiobook-metadata.png) |
| **Chapter View** — See detected speakers, override engine/voice at the chapter level, download or generate chapter audio with section-by-section progress | **Audiobook Metadata** — Set author, narrator, genre, year, description, and cover image for M4B export; re-segment with a different LLM model |
| ![Jobs Queue](docs/screenshots/jobs-queue.png) | ![Settings](docs/screenshots/settings.png) |
| **Jobs Queue** — Real-time progress tracking for generation jobs with per-segment status, playback, and waiting/processing states | **Settings** — Configure default TTS engine and voice, register remote engines, manage custom voice samples for cloning |
| ![Emotion Prosody](docs/screenshots/emotion-prosody.png) | ![Parsing Prompt](docs/screenshots/parsing-prompt.png) |
| **Emotion Prosody Settings** — Fine-tune how each of the 14+ emotions maps to pitch, speed, volume, and intensity per engine | **Parsing Prompt** — Fully editable LLM system prompt for text chunking, speaker identification, and emotion assignment |
| ![User Management](docs/screenshots/user-management.png) | |
| **User Management** — Admin panel with user accounts, role management, and invite-only registration with generated codes | |

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL
- A TTS engine (see [Supported TTS Engines](#supported-tts-engines))
- An [OpenRouter](https://openrouter.ai) API key — or any other OpenAI-compatible endpoint — for LLM-based text segmentation and speaker detection

### Docker Compose (Recommended)

```yaml
services:
   db:
      image: postgres:16-alpine
      restart: unless-stopped
      environment:
         POSTGRES_USER: ${POSTGRES_USER:-voxlibris}
         POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-voxlibris}
         POSTGRES_DB: ${POSTGRES_DB:-voxlibris}
      volumes:
         - pgdata:/var/lib/postgresql/data
      ports:
         - "${DB_PORT:-5432}:5432"
      healthcheck:
         test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-voxlibris}"]
         interval: 5s
         timeout: 5s
         retries: 5

   app:
      build: .  
      # Optionally, use the docker-build.sh script and do
      #image: narrate.ink:latest
      restart: unless-stopped
      depends_on:
         db:
            condition: service_healthy
      ports:
         - "${APP_PORT:-5000}:5000"
      environment:
         DATABASE_URL: postgresql://${POSTGRES_USER:-voxlibris}:${POSTGRES_PASSWORD:-voxlibris}@db:5432/${POSTGRES_DB:-voxlibris}
         SESSION_SECRET: ${SESSION_SECRET:-change-me-in-production}
         AI_INTEGRATIONS_OPENROUTER_BASE_URL: ${AI_INTEGRATIONS_OPENROUTER_BASE_URL:-}
         AI_INTEGRATIONS_OPENROUTER_API_KEY: ${AI_INTEGRATIONS_OPENROUTER_API_KEY:-}
         PORT: "5000"
         NODE_ENV: production
      volumes:
         - uploads:/app/uploads
         - backend-uploads:/app/backend/uploads

volumes:
   pgdata:
   uploads:
   backend-uploads:
  
```

```bash
docker compose up -d
```

Then open `http://localhost:8080` and log in with the default credentials (`Administrator` / `ChangeMe`).

> **⚠️ Change the default password immediately** via the user menu in the top-right corner.

### Local Development (JetBrains IDEs)

If you are using PyCharm, IntelliJ IDEA, or another JetBrains IDE, the repository includes pre-configured run configurations and project settings in the `.idea.example/` folder. Copy the contents of that folder into the `.idea/` directory that your IDE creates when you first open the project:

```bash
cp -r .idea.example/. .idea/
```

This gives you ready-to-use run configurations for:
- **npm dev** — starts the Node.js/Vite frontend and Express server in development mode
- **FastAPI Backend** — starts the Python backend via uvicorn with hot-reload, using the `.venv` virtual environment

After copying, reload the project in your IDE and the configurations will appear in the run dropdown.

### Connecting a TTS Engine

1. Go to **Settings** → **TTS Engine Management**
2. Enter your engine's URL (e.g., your HuggingFace Space endpoint)
3. Click **Add Engine** — narrate.ink will auto-discover the engine's capabilities
4. The engine appears in the engine table with its status, voice count, and cloning support

## Supported TTS Engines

narrate.ink uses a plugin architecture — any service implementing the [TTS Engine API contract](#tts-engine-api) works out of the box.

| Engine | Type | Voice Cloning | Emotion Support | Notes |
|--------|------|:---:|:---:|-------|
| **[Chatterbox](https://github.com/resemble-ai/chatterbox)** | Remote (GPU) | ✅ | ✅ | Expressive synthesis with exaggeration control; beats ElevenLabs in blind tests |
| **[XTTSv2](https://github.com/coqui-ai/TTS)** | Remote (GPU) | ✅ | Via prosody | Multilingual voice cloning |
| **[StyleTTS2](https://github.com/yl4579/StyleTTS2)** | Remote (GPU) | ✅ | Via diffusion presets | Style-transfer TTS |
| **[Qwen2.5/3-TTS](https://github.com/QwenLM/Qwen2.5-TTS)** | Remote (GPU) | ✅ | Via instruct prompts | Chinese/English neural TTS |
| **[OpenVoice V2](https://github.com/myshell-ai/OpenVoice)** | Remote (GPU) | ✅ | Via prosody | Voice conversion and cloning |
| **[IndexTTS2](https://github.com/indexteam/IndexTTS2)** | Remote (GPU) | ✅ | Via prosody | Indexed voice TTS |
| **Edge TTS** | Built-in (cloud) | ❌ | Partial (SSML) | Microsoft Azure neural voices — 80+ languages, no GPU required |
| **Soprano** | Built-in (local) | ❌ | ❌ | Ultra-fast local generation for quick previews |

### Running Engines on HuggingFace Spaces

The recommended way to run GPU-accelerated engines is as a [HuggingFace Space](https://huggingface.co/spaces) with a Docker runtime. Each engine in the `engines/` folder of this repository contains everything needed: a `Dockerfile`, `app.py`, `requirements.txt`, and a placeholder `index.html`.

#### Recommended hardware

**A10G · Small** is the best balance of cost and performance for audiobook generation. It handles all supported engines at real-time or faster, and costs roughly $1/hr when active. The L40S is ~80% faster but costs proportionally more — worth it only if you are generating multiple books in parallel.

#### Step-by-step: deploying an engine

1. **Create a new Space** on [huggingface.co/new-space](https://huggingface.co/new-space)
   - Set **Space SDK** to **Docker**
   - Leave everything else at defaults and click **Create Space**

2. **Clone the Space repository** locally:
   ```bash
   git clone https://huggingface.co/spaces/<your-username>/<your-space-name>
   cd <your-space-name>
   ```

3. **Copy the engine files** from the `engines/<engine-name>/` folder in this repository into the cloned Space directory:
   ```bash
   # example for Chatterbox
   cp -r /path/to/narrate.ink/engines/chatterbox/* .
   ```

4. **Commit and push** to HuggingFace:
   ```bash
   git add .
   git commit -m "Add TTS engine"
   git push
   ```
   HuggingFace will build the Docker image and start the Space automatically. The first build takes a few minutes; subsequent restarts are faster because the image is cached.

5. **Set the hardware** in the Space settings to **A10G · Small** (or larger).

#### Securing the engine with an API key

By default a running Space is publicly reachable. Anyone with the URL could use your GPU quota. To prevent this, set a secret `API_KEY` environment variable in the Space:

1. In your Space, go to **Settings → Variables and Secrets → New Secret**
2. Name it `API_KEY` and set the value to a randomly generated string — a UUID works well:
   ```bash
   python3 -c "import uuid; print(uuid.uuid4())"
   ```
3. Save the secret. The engine will now reject any request that does not include this key.

When adding the engine to narrate.ink (**Settings → TTS Engine Management**), paste the same key into the **API Token** field. narrate.ink forwards it as a Bearer token on every request.

#### Available engines

| Engine folder | Model | Voice cloning |
|---|---|:---:|
| `engines/chatterbox` | Chatterbox (Resemble AI) | ✅ |
| `engines/xttsv2` | XTTSv2 (Coqui) | ✅ |
| `engines/styletts2` | StyleTTS2 | ✅ |
| `engines/qwen25-tts` | Qwen 2.5 TTS | ✅ |
| `engines/qwen3-tts` | Qwen 3 TTS | ✅ |
| `engines/openvoice-v2` | OpenVoice V2 | ✅ |
| `engines/indextts2` | IndexTTS2 | ✅ |

narrate.ink handles cold-start warm-up automatically — it polls the engine every 5 seconds (with a 5-second per-request timeout) for up to 10 minutes, and shows a progress indicator in the Jobs view until the Space is ready.

## How It Works

### Text Analysis Pipeline

When you upload text or an EPUB, narrate.ink sends it through an LLM (via OpenRouter) that:

1. **Segments** the text into sections of ~30 chunks each
2. **Splits** each section into individual chunks at sentence and quote boundaries
3. **Classifies** each chunk as `dialogue` or `narration`
4. **Identifies speakers** for dialogue using five strategies:
   - Explicit named tags (`"Hello," said John`)
   - Compound name normalization (`Detective Chen` → `Chen`)
   - Pronoun resolution with gender and context tracking
   - Narrative context attribution to narrator
   - Turn-taking inference for rapid dialogue exchanges
5. **Labels emotions** from 14 canonical categories based on context

The parsing prompt is fully editable in Settings, so you can customize the behavior for unusual text formats or domain-specific content.

### Audio Generation Pipeline

For each chunk, narrate.ink:

1. Resolves the voice — narrator default, per-speaker assignment, or chunk-level override
2. Resolves the emotion — auto-detected, narrator override, or dialogue flattening
3. Applies prosody weights — maps the emotion to pitch/speed/volume/intensity adjustments
4. Sends the request to the TTS engine with text, voice, emotion, and prosody parameters
5. Post-processes — pitch adjustment (pyrubberband), speed adjustment, silence trimming
6. Saves as MP3 and rolls up into section → chapter audio automatically

### Settings Cascade

Settings override at every level of the hierarchy:

```
Book defaults
  └─ Chapter override
       └─ Section override
            └─ Chunk override (highest priority)
```

This means you can set a default voice for the whole book, override it for a specific chapter, and override again for a single chunk — without touching anything else.

## Configuration

### Text Segmentation (OpenRouter)

narrate.ink uses an LLM to segment, attribute, and label each chunk of text before audio generation. This requires an OpenAI-compatible API endpoint. **[OpenRouter](https://openrouter.ai)** is strongly recommended — it gives access to dozens of models (GPT-4o, Claude, Gemini, Llama, etc.) through a single API key, with pay-as-you-go pricing.

Set these two environment variables (or add them to `.env`):

```env
AI_INTEGRATIONS_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_INTEGRATIONS_OPENROUTER_API_KEY=sk-or-...
```

You can also use any other OpenAI-compatible endpoint (a local Ollama instance, vLLM, LM Studio, etc.) by changing the base URL. The model is selected per-project in the Project Wizard and can be changed at any time in the project settings.

### Environment Variables

| Variable | Required | Description |
|----------|:---:|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string (`postgresql://user:pass@host:5432/db`) |
| `SESSION_SECRET` | ✅ | Random string used to sign session cookies — generate with `openssl rand -hex 32` |
| `AI_INTEGRATIONS_OPENROUTER_BASE_URL` | Recommended | Base URL for the OpenAI-compatible LLM endpoint (default: OpenRouter) |
| `AI_INTEGRATIONS_OPENROUTER_API_KEY` | Recommended | API key for the LLM endpoint — required for text segmentation and voice analysis |
| `PORT` | No | Port the Node server listens on (default: `5000`) |
| `PYTHON_BACKEND_URL` | No | Override the Python backend URL (default: `http://127.0.0.1:8000`) |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated allowed origins for the Python backend (default: `http://localhost:5000`) |
| `OPENAI_API_KEY` | No | Required only if using OpenAI TTS voices directly |
| `VOICE_ANALYSIS_MODEL` | No | LLM model used for AI voice analysis (default: `google/gemini-2.5-flash`) |

### In-App Settings

All other configuration is managed through the Settings UI:

- **Default TTS engine and voice** — Used for new projects
- **Pause between segments** — Silence gap between chunks (0–5000ms)
- **Max silence duration** — Compress silence longer than this in final audio
- **Remote TTS engines** — Register, share, and manage external engines
- **Custom voices** — Upload WAV/MP3 samples for voice cloning
- **Voice library** — Browse and manage VCTK corpus samples
- **Emotion prosody weights** — Per-emotion pitch/speed/volume/intensity per engine
- **Parsing prompt** — LLM system prompt for text analysis
- **LLM model selection** — Choose which model to use via OpenRouter

## TTS Engine API

Any TTS service can integrate with narrate.ink by implementing two endpoints:

### `POST /GetEngineDetails`

Returns engine capabilities, available voices, and supported emotions.

```json
{
  "engine_id": "chatterbox-tts",
  "engine_name": "Chatterbox TTS",
  "sample_rate": 24000,
  "bit_depth": 16,
  "channels": 1,
  "max_seconds_per_conversion": 30,
  "supports_voice_cloning": true,
  "builtin_voices": [...],
  "supported_emotions": ["neutral", "happy", "sad", "angry", "fear", "surprise", "disgust", "excited", "calm", "confused", "anxious", "hopeful", "melancholy", "fearful"],
  "engine_params": [
    { "short_name": "exaggeration", "friendly_name": "Exaggeration", "data_type": "float", "min_value": 0.25, "max_value": 2.0, "default_value": 0.5 },
    { "short_name": "cfg_weight", "friendly_name": "CFG Weight", "data_type": "float", "min_value": 0.0, "max_value": 1.0, "default_value": 0.5 },
    { "short_name": "temperature", "friendly_name": "Temperature", "data_type": "float", "min_value": 0.05, "max_value": 5.0, "default_value": 0.8 }
  ]
}
```

### `POST /ConvertTextToSpeech`

Accepts text, voice selection, emotion, and prosody parameters; returns a PCM WAV file.

```json
{
  "input_text": "The quick brown fox jumped over the lazy dog.",
  "builtin_voice_id": "voice_001",
  "voice_to_clone_sample": null,
  "emotion_set": ["happy", "excited"],
  "intensity": 70,
  "speed_adjust": 1.5,
  "pitch_adjust": -0.5,
  "engine_options": {
    "exaggeration": 0.7,
    "cfg_weight": 0.3,
    "temperature": 0.85
  }
}
```

Engines handle emotions through three strategies:
- **Native parameter mapping** — Map emotions to engine-specific generation parameters
- **Instruct/prompt-based** — Pass emotion as a text instruction to the model
- **Prosody emulation** — Map emotions to speed/pitch adjustments for engines without native support

See the full [TTS Engine API Contract](docs/tts-api-contract.md) for the complete specification with JSON schemas.

## Cost Comparison

narrate.ink runs on your own GPU. Here's how the economics compare for producing audiobooks at volume:

| Approach | Cost for a ~80,000 word novel (~8hrs audio) | Monthly cost at 4 books/month |
|----------|---:|---:|
| **ElevenLabs Pro** ($99/mo) | ~$99+ (500K chars included, overages at $0.24/1K) | $200–400+ |
| **ElevenLabs Scale** ($330/mo) | ~$330 (2M chars included) | $330+ |
| **Human narrator** | $800–4,000 (at $100–500/finished hour) | $3,200–16,000 |
| **narrate.ink + A10G** ($1/hr GPU) | ~$4–6 (4–6 hours of GPU time) | ~$16–24 |
| **narrate.ink + L40S** ($1.80/hr GPU) | ~$5–9 (3–5 hours, faster generation) | ~$20–36 |

The more you produce, the wider the gap. narrate.ink has no per-character metering, no monthly caps, and no credit system.

## Docs

Full documentation is available in-app (click **Docs** in the header) and in the `docs/` directory:

- [Getting Started](docs/01-getting-started.md)
- [Project Wizard](docs/02-project-wizard.md)
- [Project Editor](docs/03-project-editor.md)
- [Voice Selection](docs/04-voices.md)
- [Audio Generation & Jobs](docs/05-audio-generation.md)
- [Export](docs/06-export.md)
- [Speaker Detection](docs/07-speaker-detection.md)
- [Emotion & Prosody](docs/08-emotion-prosody.md)
- [Settings](docs/09-settings.md)
- [Administration](docs/10-admin.md)
- [Tips & Shortcuts](docs/11-tips-shortcuts.md)
- [TTS Engine API Contract](docs/tts-api-contract.md)

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

## License

[MIT](LICENSE)
