# Narrator AI - Text to Audiobook Generator

## Overview

A web application that converts plain text into expressive audiobooks using AI-powered text-to-speech with:
- **edge-tts** for high-quality neural TTS (300+ voices, works without GPU)
- Voice cloning via Chatterbox TTS (when GPU available, or via external FastAPI endpoint)
- Sentiment-based pitch and speed adjustments using pyrubberband
- Automatic dialogue/narration separation
- Multi-speaker voice assignment
- Smart text chunking (~30 second intervals)

## Architecture

### Frontend (React + TypeScript)
- **Framework**: React with TypeScript
- **Styling**: Tailwind CSS with custom design tokens
- **State Management**: TanStack Query for server state
- **Routing**: Wouter
- **UI Components**: Shadcn/ui

### Backend (Python + FastAPI)
- **Framework**: FastAPI with uvicorn
- **TTS Engine**: edge-tts (Microsoft Azure Neural TTS), with Chatterbox TTS fallback for voice cloning
- **Audio Processing**: pyrubberband for pitch/speed manipulation, pydub for format conversion
- **Sentiment Analysis**: TextBlob
- **Audio I/O**: soundfile, numpy, scipy

## Project Structure

```
├── client/                 # React frontend
│   ├── src/
│   │   ├── components/    # UI components
│   │   │   ├── TextInput.tsx
│   │   │   ├── VoiceSampleManager.tsx
│   │   │   ├── VoiceLibrary.tsx
│   │   │   ├── TextPreview.tsx
│   │   │   ├── SpeakerAssignment.tsx
│   │   │   ├── AudioPlayer.tsx
│   │   │   ├── GenerationProgress.tsx
│   │   │   └── SettingsPanel.tsx
│   │   ├── pages/         # Page components
│   │   └── lib/           # Utilities
├── backend/               # Python FastAPI backend
│   ├── main.py           # FastAPI app and routes
│   ├── models.py         # Pydantic models
│   ├── text_parser.py    # Text parsing and chunking
│   ├── audio_processor.py # Pitch/speed processing
│   └── tts_service.py    # TTS generation
├── server/               # Node.js proxy server
└── shared/               # Shared TypeScript types
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/health | Health check |
| GET | /api/voices | List voice samples |
| POST | /api/voices/upload | Upload voice sample |
| DELETE | /api/voices/:id | Delete voice sample |
| GET | /api/voice-library | List pre-recorded library voices |
| GET | /api/edge-voices | List available edge-tts neural voices |
| GET | /api/openai-voices | List available OpenAI TTS voices |
| POST | /api/parse-text | Parse text into segments |
| POST | /api/generate | Generate audiobook |

## Key Features

1. **Text Parsing**: Separates dialogue (quotes) from narration, identifies speakers using dialogue verbs

2. **Emotion-Based Prosody**: Applies subtle pitch and speed adjustments based on detected emotion:
   
   | Emotion    | Pitch    | Speed    | Description                    |
   |------------|----------|----------|--------------------------------|
   | neutral    |  0%      |  0%      | No adjustment                  |
   | happy      | +1%      | +1%      | Joy, pleasure, positive        |
   | sad        | -1%      | -1%      | Sorrow, disappointment, loss   |
   | angry      | +1%      | +1%      | Frustration, confrontation     |
   | fearful    | +1%      | +1%      | Fear, worry, danger            |
   | surprised  | +1%      | +1%      | Shock, astonishment            |
   | disgusted  | -1%      | -1%      | Revulsion, distaste            |
   | excited    | +1%      | +1%      | Enthusiasm, anticipation       |
   | calm       |  0%      | -1%      | Peaceful, serene               |
   | anxious    | +0.5%    | +1%      | Nervousness, tension           |
   | hopeful    | +0.5%    |  0%      | Optimism, looking forward      |
   | melancholy | -0.5%    | -1%      | Wistful sadness, nostalgia     |

3. **Smart Chunking**: Splits text at natural break points:
   - Sentence endings (. ! ?)
   - Colons/semicolons
   - Commas
   - Conjunctions (and, but, or)
   - Between words (last resort)

4. **Voice Cloning**: Uses 7-20 second audio samples for voice cloning via Chatterbox

5. **Voice Library**: Pre-uploaded voice samples from the VCTK corpus in `voice_samples/` folder:
   - Format: `p{number}_mic1.wav` and `p{number}_mic2.wav` audio files
   - Metadata in transcript files: `p{number}_{gender}_{age}_{language}_{location}.txt`
   - Display format: "Voice 226: M/22 Surrey, England"
   - Features: preview playback, search/filter by gender, role assignment

## Running the Application

The application requires both the Python backend and Node.js frontend to run:

1. **Python Backend** (port 8000):
   ```bash
   cd backend && python main.py
   ```

2. **Node.js Frontend** (port 5000):
   ```bash
   npm run dev
   ```

Or use the combined start script:
```bash
./start.sh
```

## Environment Variables

- `PORT`: Frontend port (default: 5000)
- `PYTHON_BACKEND_URL`: Backend URL (default: http://127.0.0.1:8000)

## Recent Changes

- **2026-01-26**: LLM parsing chunk optimization
  - Reduced batch size from 10 paragraphs to 2-3 paragraphs per LLM call
  - Quote-aware splitting prevents mid-dialogue cuts (tracks straight quotes via parity, curly quotes via balance)
  - Runaway batch prevention: capped at 6 paragraphs (2x target) if quotes never balance
  - More granular progress updates during LLM parsing phase
- **2026-01-26**: Streaming progress and audio quality improvements
  - Real-time progress updates via Server-Sent Events (SSE) with asyncio.Queue
  - Progress bar now updates incrementally during generation (not 0%→100% jumps)
  - Trailing silence trimming on audio chunks using RMS analysis (50ms blocks, 0.01 threshold)
  - Voice ID prefix system: `edge:`, `openai:`, `library:` for engine-specific voices
  - Dynamic voice dropdowns update based on selected TTS engine
  - 10-minute SSE timeout for long audiobook generation
- **2026-01-26**: Chatterbox TTS split into free and paid tiers
  - **Chatterbox Free**: Uses HuggingFace Spaces via Gradio API, 300 char limit
  - **Chatterbox Paid**: Custom API endpoint, no char limit, requires config
  - Configuration via environment variables: CHATTERBOX_API_URL, CHATTERBOX_API_KEY
  - `/api/chatterbox-status` endpoint for checking configuration
  - Frontend shows warning when paid is selected but not configured
  - Falls back to free tier if paid API not available
- **2026-01-26**: Chatterbox voice cloning via HuggingFace Spaces
  - Uses gradio_client to connect to ResembleAI/Chatterbox Space
  - No GPU required - runs in cloud via Gradio API
  - Supports voice cloning with audio reference files
  - Falls back from local Chatterbox → Gradio API → edge-tts → sine wave
  - 300 character limit per generation (auto-truncated)
  - Configurable exaggeration, temperature, and CFG weight
- **2026-01-26**: Multi-engine TTS selection with improved fallback chain
  - TTS Engine dropdown in Settings: Edge TTS (default), OpenAI, Chatterbox, Piper
  - Voice Library dynamically updates based on selected engine
  - OpenAI TTS with 6 premium voices (alloy, echo, fable, onyx, nova, shimmer)
  - Improved fallback chain: selected engine → edge-tts → sine wave (better quality)
  - OpenAI voice mapping validates voice names before API calls
  - Piper TTS checks for CLI availability before attempting generation
  - New `/api/openai-voices` endpoint for listing OpenAI TTS voices
- **2026-01-26**: Integrated edge-tts as primary TTS engine
  - Microsoft Azure Neural TTS with 300+ voices (47 English voices)
  - Works without GPU, high-quality speech synthesis
  - Automatic fallback from Chatterbox when not available
  - New `/api/edge-voices` endpoint lists all available neural voices
  - Preset voices for common use cases (narrator, male/female US/UK/AU)
  - Ready for future Chatterbox FastAPI endpoint integration
- **2026-01-25**: Major LLM parsing upgrade with ChatGPT and speaker confidence scores
  - Default model changed to ChatGPT 4o (via OpenRouter)
  - New JSON output format with speaker confidence scores (e.g., {"Shane": 0.95, "Ilya": 0.05})
  - Segments flagged for review when speaker confidence variance is low
  - ~30 second audio chunks at natural stopping points (speaker/narration transitions)
  - Conversational LLM context: parses ~10 paragraphs per prompt, maintaining character context
  - Sentiment analysis included in LLM output
  - UI shows "needs review" badges for uncertain speaker assignments
  - Tooltip shows full confidence breakdown on hover
- **2026-01-25**: Enhanced LLM speaker detection with chunking and name hints
  - Text is now split into ~2000 char chunks at safe boundaries (avoids splitting quotes)
  - Automatic name extraction finds potential speakers using dialogue verb patterns
  - Users can optionally provide known speaker names to guide the AI
- **2026-01-25**: Added LLM-powered speaker detection via OpenRouter integration
  - Users can choose between AI Detection (LLM) and Basic (heuristic) modes
  - Model selection dropdown with Llama, Mistral, Qwen, DeepSeek options
  - Automatic fallback to basic parsing if LLM fails
- **2026-01-25**: Fixed curly/smart quote detection (", ")
- **2026-01-25**: Improved speaker detection - now checks text after quotes first (e.g., "Hello!" said John)
- **2026-01-25**: Added smart text chunking with ~30s target and priority-based split points
- **2026-01-25**: Fixed API response parsing bug in frontend
- **2026-01-25**: Integrated sentiment-driven prosody in TTS pipeline
- Initial implementation with React frontend and Python backend
- Text parsing with sentiment analysis
- Voice sample upload and management
- Audio generation with prosody adjustments
- Dark mode support

## User Preferences

- Modern, professional design with purple/violet theme
- Clean UI with proper spacing and typography
- Responsive layout
