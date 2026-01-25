# Narrator AI - Text to Audiobook Generator

## Overview

A web application that converts plain text into expressive audiobooks using AI-powered text-to-speech with:
- Voice cloning via Chatterbox TTS (when GPU available)
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
- **TTS Engine**: Chatterbox TTS (Resemble AI)
- **Audio Processing**: pyrubberband for pitch/speed manipulation
- **Sentiment Analysis**: TextBlob
- **Audio I/O**: soundfile, numpy, scipy

## Project Structure

```
├── client/                 # React frontend
│   ├── src/
│   │   ├── components/    # UI components
│   │   │   ├── TextInput.tsx
│   │   │   ├── VoiceSampleManager.tsx
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
| POST | /api/parse-text | Parse text into segments |
| POST | /api/generate | Generate audiobook |

## Key Features

1. **Text Parsing**: Separates dialogue (quotes) from narration, identifies speakers using dialogue verbs

2. **Sentiment Analysis**: Analyzes text sentiment to apply emotional prosody:
   - Positive → slight pitch up, faster
   - Negative → pitch down, slower
   - Excited → higher pitch, faster
   - Sad → lower pitch, slower
   - Angry → pitch up, faster
   - Fearful → pitch up, faster

3. **Smart Chunking**: Splits text at natural break points:
   - Sentence endings (. ! ?)
   - Colons/semicolons
   - Commas
   - Conjunctions (and, but, or)
   - Between words (last resort)

4. **Voice Cloning**: Uses 7-20 second audio samples for voice cloning via Chatterbox

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
