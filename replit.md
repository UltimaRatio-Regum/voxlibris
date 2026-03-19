# VoxLibris - Text to Audiobook Generator

## Overview
VoxLibris is a web application that transforms plain text into expressive audiobooks using advanced AI-powered text-to-speech (TTS) technologies. It provides high-quality, customizable audiobook generation with features like multi-speaker assignment, sentiment-based prosody adjustments, and smart text chunking. The project aims to offer a seamless user experience for converting various text formats, including EPUBs, into engaging audio content, utilizing both neural and local TTS engines.

## User Preferences
- Modern, professional design with purple/violet theme
- Clean UI with proper spacing and typography
- Responsive layout

## System Architecture

### Frontend (React + TypeScript)
- **Framework**: React with TypeScript, styled with Tailwind CSS and Shadcn/ui components.
- **State Management**: TanStack Query for server state; Wouter for routing.
- **UI/UX Decisions**: Four-tab layout (Project Wizard, Projects, Jobs, Settings) + admin-only Users tab; wizard-style generation flow (Upload → Analyzing → Voice Selection → Generate); real-time progress updates; dark mode support. A "Docs" button in the header links to the in-app documentation.
- **Documentation Site**: Publicly accessible at `/docs` and `/docs/:slug` (no auth required). Renders markdown files from the `docs/` directory with YAML frontmatter (title, description, category, order, keywords). Features: categorized sidebar with collapsible sections, search/filter, cross-document linking, "On This Page" heading navigation, prev/next pagination, responsive mobile sidebar, dark mode. Backend serves `GET /api/docs/manifest` (doc list) and `GET /api/docs/:slug` (doc content). Uses `react-markdown`, `remark-gfm`, `rehype-raw`, `gray-matter`. Key file: `client/src/pages/DocsPage.tsx`.
- **Project Wizard Tab**: Guided four-step wizard (Upload → Analyzing → Voice Selection → Generate) that creates a real project behind the scenes, runs LLM segmentation, lets the user assign voices (single or per-character), then starts audio generation and navigates to the project editor.
- **Projects Tab**: Manages audiobook projects, supporting text/EPUB imports. Features a two-panel editor for hierarchical content (Book → Chapters → Sections → Chunks), allowing settings overrides and audio generation at various levels. Includes audiobook metadata editing, cover image upload, and export options (single MP3, MP3 per chapter ZIP, M4B with chapters). Speaker voice assignment and a "Speaker Inspector Dialog" for managing and merging speakers are integrated.
- **Settings Tab**: Configures default TTS engine/voice, manages custom voices, sets emotion prosody weights, allows registration/management of external TTS engines, and provides an editable parsing/speaker-identification prompt for customizing LLM text analysis behavior.
- **TTS Engine Configuration**: Centralized management of built-in (Edge TTS, Soprano) and remote TTS engines, supporting dynamic registration and integration into voice selection.

### Backend (Python + FastAPI)
- **Framework**: FastAPI with uvicorn.
- **Built-in TTS Engines**: Integrates `edge-tts` (Microsoft Azure) and Soprano TTS for high-quality and ultra-fast local generation, respectively.
- **Remote TTS Engines**: Supports a REST DI system for registering external TTS services, including automatic warm-up polling and cancellation during wake-up. Specific engine implementations (XTTSv2, Qwen2.5/3-TTS, OpenVoice V2, Chatterbox, StyleTTS2, IndexTTS2) are provided as deployable HuggingFace Space endpoints.
- **Base Voice / Language**: Allows selection of a base voice for engines that separate base speech generation from voice cloning, controlling language/accent independently.
- **TTS Architecture**: Uses a base class pattern for TTS engines, standardizing parameters (text, voice_wav, voice_text, voice_id, speed, pitch, emotion, exaggeration) and allowing engine-specific logic.
- **Audio Processing**: Utilizes pyrubberband for pitch/speed, pydub for format conversion, and aggressive silence trimming.
- **Emotion Analysis**: Assigns 14 canonical emotions per text chunk using an LLM, with TextBlob as a fallback. Supports narrator emotion override (force a single emotion for all narration segments) and dialogue emotion flattening (unify emotion across contiguous same-speaker dialogue chunks via first-chunk or word-count-majority modes).
- **Text Processing**: Unified LLM-based segmentation and chunking (8-12 second chunks) with quote-boundary splitting, per-chunk emotion, and speaker identification. Includes non-LLM fallbacks and project-level segmentation into sections with LLM-generated titles. Speaker identification employs 5 strategies: explicit named dialogue tags (with cleaned context), multi-word speaker names, pronoun-based resolution with turn-taking (supports same-speaker continuation), narrative context detection, and turn-taking inference. Post-processing normalizes speaker names (e.g. "Detective Chen" → "Chen"). Supports per-section re-chunking with LLM retry logic (3 attempts) and raw text preservation; section detail panel exposes a re-chunk button with model selection.
- **Editable Parsing Prompt**: The LLM system prompt for text chunking and speaker identification is user-editable and persisted.
- **Job Management**: Asynchronous TTS generation jobs run in background threads, with database persistence (SQLAlchemy) for jobs and segments. Supports real-time progress, partial playback, and job lifecycle management. Jobs are split per section for parallel processing, and audio is recursively rolled up from chunks to sections to chapters for combined playback. TTSJob has a `job_type` field (`tts` or `export`) to unify TTS generation and audiobook export jobs in a single Jobs tab. Export jobs run in background threads via `export_runner.py`, store output in `ProjectAudioFile` with `scope_type="export"`, and support download from the Jobs panel.
- **File Handling**: Supports `.txt` and `.epub` files with automatic chapter extraction.
- **API Endpoints**: Comprehensive RESTful API for managing voices, text parsing, audio generation, and job status.

### Deployable Engine Endpoints (`engines/`)
- A collection of HuggingFace Space Docker SDK implementations for various TTS models (e.g., XTTSv2, Qwen2.5/3-TTS, OpenVoice V2, Chatterbox, StyleTTS2, IndexTTS2). These provide REST APIs adhering to the VoxLibris TTS API Contract, supporting voice cloning, emotion prompting, and other features, designed for external deployment and registration.

### Authentication & Multi-User System
- **Auth**: Passport.js local strategy with bcrypt passwords; express-session + connect-pg-simple for session storage (30-day sessions).
- **User Roles**: `user` (default) and `administrator`.
- **Registration Modes**: `disabled` (default), `invite-only`, `open` — stored in `system_settings` table.
- **Seed Account**: Username `Administrator`, password `ChangeMe`, created on first startup if no users exist.
- **Data Isolation**: Projects, custom voices filtered by `user_id`; TTS engines have `is_shared` flag (shared engines visible to all, private engines visible to owner only); admins see everything.
- **Auth Flow**: Express routes at `/api/auth/*` (login, logout, register, me, change-password, registration-mode); admin routes at `/api/admin/*` (users CRUD, invitation codes, registration mode settings).
- **Header Forwarding**: Express proxy injects `X-User-Id` and `X-User-Role` headers for the Python backend.
- **Key Files**: `server/auth.ts` (auth setup), `client/src/lib/auth.tsx` (AuthProvider/useAuth), `client/src/pages/AdminUsersPage.tsx` (admin UI), `client/src/components/ChangePasswordDialog.tsx`.
- **Database Tables**: `users`, `invitation_codes`, `system_settings`; added `user_id` FK to `projects`, `custom_voices`, `tts_engine_endpoints`; added `is_shared` to `tts_engine_endpoints`, `voice_library`.
- **Dependencies**: `bcryptjs`, `@types/bcryptjs`, `passport`, `passport-local`, `@types/passport-local`, `express-session`, `@types/express-session`, `connect-pg-simple`, `@types/connect-pg-simple`, `uuid`, `@types/uuid` (Node); `bcrypt` (Python).

## External Dependencies
- **Microsoft Azure Neural TTS**: Integrated via `edge-tts`.
- **Soprano TTS**: Local TTS model.
- **OpenRouter**: Used for LLM-powered text parsing and speaker detection.
- **PostgreSQL**: Primary database for job persistence and data management.
- **VTCK Corpus**: Provides pre-recorded voice samples for the voice library.