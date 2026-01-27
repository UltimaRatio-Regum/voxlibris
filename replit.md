# Narrator AI - Text to Audiobook Generator

## Overview
Narrator AI is a web application designed to transform plain text into expressive audiobooks using advanced AI-powered text-to-speech (TTS) technologies. Its core purpose is to provide high-quality, customizable audiobook generation, incorporating features like multi-speaker assignment, sentiment-based prosody adjustments, and smart text chunking. The project aims to deliver a seamless user experience for converting various text formats, including EPUBs, into engaging audio content, leveraging both neural and local TTS engines for flexibility and performance.

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
- **UI/UX Decisions**: Three-tab layout (Beginner, Advanced, Job Monitor), file upload workflow, wizard-style generation flow (Upload → Analyzing → Voice Selection → Generate), real-time progress updates, dark mode support.

### Backend (Python + FastAPI)
- **Framework**: FastAPI with uvicorn
- **TTS Engines**:
    - **edge-tts**: High-quality neural TTS (Microsoft Azure), 300+ voices.
    - **Soprano TTS**: Ultra-fast local generation (80M model, 2000x real-time on GPU).
    - **Chatterbox TTS**: Voice cloning (via HuggingFace Spaces API or local when GPU available), supports emotion-based exaggeration.
    - **OpenAI TTS**: Utilizes 6 premium voices.
    - **Piper TTS**: Local TTS engine.
- **Audio Processing**: pyrubberband for pitch/speed manipulation, pydub for format conversion, soundfile, numpy, scipy for audio I/O. Aggressive silence trimming for TTS audio (two-pass removal and edge trimming).
- **Sentiment Analysis**: TextBlob, integrated into LLM output for emotion-based prosody adjustments.
- **Text Processing**: Smart chunking (sentence endings, colons/semicolons, commas, conjunctions, word-based), dialogue/narration separation, speaker identification using LLMs (e.g., ChatGPT 4o via OpenRouter) with confidence scores, automatic name extraction, and user-provided name hints.
- **Job Management**: Asynchronous TTS generation jobs running in background threads, with database persistence (SQLAlchemy) for jobs and segments. Real-time progress tracking, partial playback of segments, and job lifecycle management (create, list, cancel, delete).
- **File Handling**: Support for `.txt` and `.epub` files with automatic chapter extraction (using `ebooklib`).
- **API Endpoints**: Comprehensive RESTful API for managing voices, text parsing, generating audiobooks, and monitoring job status.

## External Dependencies
- **Microsoft Azure Neural TTS**: (via `edge-tts`)
- **Soprano TTS**: (ekwek/Soprano-1.1-80M)
- **Chatterbox TTS**: HuggingFace Spaces (Gradio API for Free tier, custom API for Paid tier)
- **OpenAI TTS API**
- **Piper TTS CLI**
- **OpenRouter**: For LLM-powered text parsing and speaker detection (e.g., ChatGPT 4o, Llama, Mistral, Qwen, DeepSeek).
- **PostgreSQL**: For job persistence and database management.
- **VTCK Corpus**: Pre-recorded voice samples for the voice library.