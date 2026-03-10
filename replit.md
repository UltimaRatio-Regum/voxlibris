# VoxLibris - Text to Audiobook Generator

## Overview
VoxLibris is a web application designed to transform plain text into expressive audiobooks using advanced AI-powered text-to-speech (TTS) technologies. Its core purpose is to provide high-quality, customizable audiobook generation, incorporating features like multi-speaker assignment, sentiment-based prosody adjustments, and smart text chunking. The project aims to deliver a seamless user experience for converting various text formats, including EPUBs, into engaging audio content, leveraging both neural and local TTS engines for flexibility and performance.

## User Preferences
- Modern, professional design with purple/violet theme
- Clean UI with proper spacing and typography
- Responsive layout

## System Architecture

### Frontend (React + TypeScript)
- **Framework**: React with TypeScript
- **Styling**: Tailwind CSS with custom design tokens
- **State Management**: TanStack Query for server state
- **Routing**: Wouter
- **UI Components**: Shadcn/ui
- **UI/UX Decisions**: Four-tab layout (Beginner, Advanced, Jobs, Settings), file upload workflow, wizard-style generation flow (Upload → Analyzing → Voice Selection → Generate), real-time progress updates, dark mode support.
- **Advanced Tab Layout**: Two-column grid. Left: TextInput → TextPreview. Right: Generation Settings (engine, intensity, pause) → Voice Assignment (appears after text analysis, with narrator + detected speaker dropdowns, inline "Upload New Voice" option).
- **Settings Tab**: Default TTS engine/voice selection (persisted to localStorage), Custom Voices management (upload/rename/delete/play), emotion prosody configuration table with pitch/speed/volume weights (persisted to prosody_settings.json), engine registration (REST DI), voice library browser.
- **TTS Engine Configuration**: Centralized in `client/src/lib/tts-engines.ts` with `TTS_ENGINES` array defining built-in engines (Edge TTS, Soprano). Registered remote engines fetched from `/api/tts-engines` and merged into engine dropdowns in both Advanced and Beginner tabs. `RegisteredEngine` type exported from `SettingsPanel.tsx`. Helper functions: `isVoiceCloningEngine()`, `getTTSEngine()`, `getVoiceCloningEngines()`, `getLocalEngines()`.

### Backend (Python + FastAPI)
- **Framework**: FastAPI with uvicorn
- **Built-in TTS Engines**:
    - **edge-tts**: High-quality neural TTS (Microsoft Azure), 300+ voices.
    - **Soprano TTS**: Ultra-fast local generation (80M model, 2000x real-time on GPU).
- **Remote TTS Engines**: Registered via REST DI system (URL + optional API key). `RemoteTTSClient` in `backend/remote_tts_client.py` auto-normalizes HuggingFace Spaces page URLs to API endpoints. Legacy backend engine classes (Chatterbox, HF TTS Paid, StyleTTS2, OpenAI, Piper) remain in `backend/tts_engines.py` but are not exposed in the frontend engine list.
- **TTS Architecture**: Base class pattern in `backend/tts_engines.py` with unified TTSParams (text, voice_wav, voice_text, voice_id, speed, pitch, emotion, exaggeration). Engine subclasses implement engine-specific logic. EngineFactory creates instances by name.
- **Audio Processing**: pyrubberband for pitch/speed manipulation, pydub for format conversion, soundfile, numpy, scipy for audio I/O. Aggressive silence trimming for TTS audio (two-pass removal and edge trimming).
- **Emotion Analysis**: 14 canonical emotions (neutral, happy, sad, angry, fear, disgust, surprise, excited, calm, anxious, hopeful, melancholy, tender, proud). LLM assigns per-chunk emotions in a single pass; TextBlob fallback uses keyword matching + polarity.
- **Text Processing**: Unified segmentation+chunking in one LLM pass producing 8-12 second chunks with quote-boundary splitting, per-chunk emotion, and speaker identification. Non-LLM fallback: regex quote splitting → paragraph splitting → smart chunking (~10s target, priority: sentence endings, colons/semicolons, commas, conjunctions). Known speakers accumulated across chapters for long-form content.
- **Job Management**: Asynchronous TTS generation jobs running in background threads, with database persistence (SQLAlchemy) for jobs and segments. Real-time progress tracking, partial playback of segments, and job lifecycle management (create, list, cancel, delete).
- **File Handling**: Support for `.txt` and `.epub` files with automatic chapter extraction (using `ebooklib`).
- **API Endpoints**: Comprehensive RESTful API for managing voices, text parsing, generating audiobooks, and monitoring job status.

### Deployable Engine Endpoints (`engines/`)
- **engines/xttsv2/**: HuggingFace Space (Docker SDK) serving Coqui XTTSv2 as a REST API implementing the VoxLibris TTS API Contract. Files: `app.py` (FastAPI), `Dockerfile`, `requirements.txt`, `README.md`. Supports voice cloning via base64 WAV, emotion prompting, speed/volume control, 16 languages. Deploy to HF Spaces, then register the URL in VoxLibris Settings.
- **engines/qwen25-tts/**: HuggingFace Space (Docker SDK) serving Qwen2.5-Omni-7B as a REST API implementing the VoxLibris TTS API Contract. Files: `app.py` (FastAPI), `Dockerfile`, `requirements.txt`, `README.md`. Built-in voices (Chelsie, Ethan), voice cloning via audio conditioning, emotion prompting, pyrubberband speed/pitch adjustment, 16 languages. Requires GPU (A10G+). Deploy to HF Spaces, then register the URL in VoxLibris Settings.
- **engines/qwen3-tts/**: HuggingFace Space (Docker SDK) serving Qwen3-TTS-12Hz-1.7B as a REST API implementing the VoxLibris TTS API Contract. Uses `qwen_tts` package with `Qwen3TTSModel`. Two models loaded: CustomVoice (9 built-in speakers with instruct-based emotion) and Base (voice cloning via x-vector). Files: `app.py` (FastAPI), `Dockerfile`, `requirements.txt`, `index.html`, `README.md`. 9 voices (Ryan, Aiden, Vivian, Serena, Uncle Fu, Dylan, Eric, Ono Anna, Sohee), pyrubberband speed/pitch. Requires GPU (L4+). Deploy to HF Spaces, then register the URL in VoxLibris Settings.
- **engines/openvoice-v2/**: HuggingFace Space (Docker SDK) serving MyShell OpenVoice V2 as a REST API implementing the VoxLibris TTS API Contract. Two-stage architecture: MeloTTS for base speech generation + ToneColorConverter for instant voice cloning. Files: `app.py` (FastAPI), `Dockerfile`, `requirements.txt`, `index.html`, `README.md`. 10 built-in voices across 6 languages (EN, ES, FR, ZH, JP, KR), pyrubberband pitch adjustment, native speed control. Lightweight (~500 MB), runs on CPU or GPU. Deploy to HF Spaces, then register the URL in VoxLibris Settings.
- **engines/chatterbox/**: HuggingFace Space (Docker SDK) serving Chatterbox TTS as a REST API implementing the VoxLibris TTS API Contract. Files: `app.py` (FastAPI), `Dockerfile`, `requirements.txt`, `index.html` (test console), `README.md`. Voice cloning only (requires reference audio). Full emotion-to-parameter mapping: emotion→exaggeration (0.0-1.0), emotion→cfg_weight, emotion→temperature, plus emotion→speed/pitch prosody reinforcement. 300 char limit per request, pyrubberband speed/pitch. Requires GPU (T4+). Deploy to HF Spaces, then register the URL in VoxLibris Settings.
- **engines/styletts2/**: HuggingFace Space (Docker SDK) serving StyleTTS2 as a REST API implementing the VoxLibris TTS API Contract. Uses `styletts2` PyPI package (v0.1.6+) with LibriTTS multi-speaker model. Emotion control via diffusion parameter presets (alpha/beta/embedding_scale/diffusion_steps) for 9 emotions (neutral, happy, sad, angry, fear, excited, calm, surprised, whisper). Voice cloning via reference audio. Long-form inference with style continuity. Requires GPU (T4+). Python 3.10, pinned dependencies for compatibility. Deploy to HF Spaces, then register the URL in VoxLibris Settings.

## Docker Deployment

The app can be run with Docker and Docker Compose. The setup includes:
- **Dockerfile**: Multi-stage build (Node.js frontend build → Python deps → combined runtime). Produces a single image that runs both the Express server and the Python FastAPI backend.
- **docker-compose.yml**: Orchestrates the app container and a PostgreSQL 16 database with a persistent volume.
- **docker-entrypoint.sh**: Startup script that launches the Python backend, waits for it to be healthy, then starts the Node.js server.
- **.env.example**: Template for environment variables (copy to `.env` and fill in).

### Quick Start
```bash
cp .env.example .env        # Edit .env with your secrets
docker compose up --build    # Build and start all services
```

The app will be available at `http://localhost:5000`. PostgreSQL runs internally on port 5432 (mapped to host via `DB_PORT`).

### Environment Variables
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`: Database credentials (defaults: `voxlibris`)
- `SESSION_SECRET`: Express session secret (required for production)
- `AI_INTEGRATIONS_OPENROUTER_BASE_URL`, `AI_INTEGRATIONS_OPENROUTER_API_KEY`: Optional, for LLM-powered speaker detection
- `APP_PORT`: Host port for the app (default: 5000)
- `DB_PORT`: Host port for PostgreSQL (default: 5432)

## External Dependencies
- **Microsoft Azure Neural TTS**: (via `edge-tts`)
- **Soprano TTS**: (ekwek/Soprano-1.1-80M)
- **Chatterbox TTS**: HuggingFace Spaces (Gradio API for Free tier, custom API for Paid tier)
- **OpenAI TTS API**
- **Piper TTS CLI**
- **OpenRouter**: For LLM-powered text parsing and speaker detection (e.g., ChatGPT 4o, Llama, Mistral, Qwen, DeepSeek).
- **PostgreSQL**: For job persistence and database management.
- **VTCK Corpus**: Pre-recorded voice samples for the voice library.