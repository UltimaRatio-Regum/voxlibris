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
- **Settings Tab**: Default TTS engine/voice selection (persisted to localStorage), emotion prosody configuration table with pitch/speed/volume weights (persisted to prosody_settings.json).
- **TTS Engine Configuration**: Centralized in `client/src/lib/tts-engines.ts` with `TTS_ENGINES` array defining all engines with properties (id, label, name, description, badge, supportsVoiceCloning, requiresApiKey, isLocal). Helper functions: `isVoiceCloningEngine()`, `getTTSEngine()`, `getVoiceCloningEngines()`, `getLocalEngines()`.

### Backend (Python + FastAPI)
- **Framework**: FastAPI with uvicorn
- **TTS Engines**:
    - **edge-tts**: High-quality neural TTS (Microsoft Azure), 300+ voices.
    - **Soprano TTS**: Ultra-fast local generation (80M model, 2000x real-time on GPU).
    - **Chatterbox Free**: Voice cloning (via HuggingFace Spaces API), supports emotion-based exaggeration.
    - **HuggingFace TTS Paid**: Multi-model voice cloning (Qwen3, Chatterbox, XTTS v2, StyleTTS2) with Bearer token auth.
    - **StyleTTS2**: Standalone expressive TTS via CherithCutestory/styletts2 HF Space, supports emotion control (neutral, happy, sad, angry, fear, excited), native speed/pitch adjustment (no pyrubberband needed).
    - **OpenAI TTS**: Utilizes 6 premium voices.
    - **Piper TTS**: Local TTS engine.
- **TTS Architecture**: Base class pattern in `backend/tts_engines.py` with unified TTSParams (text, voice_wav, voice_text, voice_id, speed, pitch, emotion, exaggeration). Engine subclasses implement engine-specific logic. EngineFactory creates instances by name.
- **Audio Processing**: pyrubberband for pitch/speed manipulation, pydub for format conversion, soundfile, numpy, scipy for audio I/O. Aggressive silence trimming for TTS audio (two-pass removal and edge trimming).
- **Sentiment Analysis**: TextBlob, integrated into LLM output for emotion-based prosody adjustments.
- **Text Processing**: Smart chunking (sentence endings, colons/semicolons, commas, conjunctions, word-based), dialogue/narration separation, speaker identification using LLMs (e.g., ChatGPT 4o via OpenRouter) with confidence scores, automatic name extraction, and user-provided name hints.
- **Job Management**: Asynchronous TTS generation jobs running in background threads, with database persistence (SQLAlchemy) for jobs and segments. Real-time progress tracking, partial playback of segments, and job lifecycle management (create, list, cancel, delete).
- **File Handling**: Support for `.txt` and `.epub` files with automatic chapter extraction (using `ebooklib`).
- **API Endpoints**: Comprehensive RESTful API for managing voices, text parsing, generating audiobooks, and monitoring job status.

### Deployable Engine Endpoints (`engines/`)
- **engines/xttsv2/**: HuggingFace Space (Docker SDK) serving Coqui XTTSv2 as a REST API implementing the VoxLibris TTS API Contract. Files: `app.py` (FastAPI), `Dockerfile`, `requirements.txt`, `README.md`. Supports voice cloning via base64 WAV, emotion prompting, speed/volume control, 16 languages. Deploy to HF Spaces, then register the URL in VoxLibris Settings.
- **engines/qwen25-tts/**: HuggingFace Space (Docker SDK) serving Qwen2.5-Omni-7B as a REST API implementing the VoxLibris TTS API Contract. Files: `app.py` (FastAPI), `Dockerfile`, `requirements.txt`, `README.md`. Built-in voices (Chelsie, Ethan), voice cloning via audio conditioning, emotion prompting, pyrubberband speed/pitch adjustment, 16 languages. Requires GPU (A10G+). Deploy to HF Spaces, then register the URL in VoxLibris Settings.
- **engines/qwen3-tts/**: HuggingFace Space (Docker SDK) serving Qwen3-TTS-12Hz-1.7B as a REST API implementing the VoxLibris TTS API Contract. Uses `qwen_tts` package with `Qwen3TTSModel`. Two models loaded: CustomVoice (9 built-in speakers with instruct-based emotion) and Base (voice cloning via x-vector). Files: `app.py` (FastAPI), `Dockerfile`, `requirements.txt`, `index.html`, `README.md`. 9 voices (Ryan, Aiden, Vivian, Serena, Uncle Fu, Dylan, Eric, Ono Anna, Sohee), pyrubberband speed/pitch. Requires GPU (L4+). Deploy to HF Spaces, then register the URL in VoxLibris Settings.

## External Dependencies
- **Microsoft Azure Neural TTS**: (via `edge-tts`)
- **Soprano TTS**: (ekwek/Soprano-1.1-80M)
- **Chatterbox TTS**: HuggingFace Spaces (Gradio API for Free tier, custom API for Paid tier)
- **OpenAI TTS API**
- **Piper TTS CLI**
- **OpenRouter**: For LLM-powered text parsing and speaker detection (e.g., ChatGPT 4o, Llama, Mistral, Qwen, DeepSeek).
- **PostgreSQL**: For job persistence and database management.
- **VTCK Corpus**: Pre-recorded voice samples for the voice library.