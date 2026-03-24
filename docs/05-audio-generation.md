---
title: Audio Generation & Jobs
description: Generate audio, monitor jobs, and manage the generation queue
category: Audio
order: 5
keywords: [generation, jobs, TTS, audio, progress, queue, background]
---

# Audio Generation & Jobs

Audio generation in TomeVox runs as background jobs, allowing you to continue working while audio is being created.

## Starting Generation

You can generate audio at multiple levels:

### From the Project Wizard
The wizard creates a generation job for the entire project after voice assignment.

### From the Project Editor
Generate audio for specific parts of your project:

- **Entire project** — Generates all chunks
- **Chapter** — Generates all chunks in a chapter
- **Section** — Generates all chunks in a section
- **Individual chunk** — Regenerate a single chunk

### Generation Settings

Before starting generation, you can configure:

| Setting | Description |
|---------|-------------|
| **TTS Engine** | Which engine to use (Edge TTS, Soprano, remote engine) |
| **Voice** | The voice to use for generation |
| **Speed** | Playback speed adjustment (0.5x - 2.0x) |
| **Pitch** | Pitch adjustment |
| **Emotion** | Emotion intensity for supported engines |
| **Engine-specific params** | Additional controls declared by the engine (e.g., Chatterbox exposes `Exaggeration`, `CFG Weight`, and `Temperature`). These are discovered automatically when the engine is registered and override the default emotion-to-parameter mapping when set. |

## Monitoring Jobs

### Jobs Tab
The **Jobs** tab shows all your generation and export jobs:

- **Status** — Waiting, Running, Completed, or Failed
- **Progress** — Number of completed segments vs. total
- **Type** — TTS generation or audiobook export
- **Timing** — When the job started and its duration

### Real-time Progress
Active jobs update in real-time showing:
- Current chunk being processed
- Completed/total segment counts
- Estimated time remaining

### Job Pagination
Jobs are paginated for performance. Use the navigation controls to browse through your job history.

## Audio Processing Pipeline

When a chunk is generated, TomeVox applies several processing steps:

1. **TTS synthesis** — The engine generates raw speech audio
2. **Pitch adjustment** — Applied via pyrubberband if a pitch offset is set
3. **Speed adjustment** — Applied via pyrubberband if speed differs from 1.0x
4. **Silence trimming** — Aggressive trimming of leading/trailing silence
5. **Format conversion** — Final audio saved as MP3

## Audio Rollup

Generated audio is automatically combined (rolled up) at higher levels:

- **Chunk audio** → combined into **Section audio**
- **Section audio** → combined into **Chapter audio**

This means you can play back an entire chapter or section without gaps.

## Partial Playback

You don't need to wait for an entire job to finish. As soon as individual chunks complete, you can:

- Play completed chunks immediately
- Listen to partially completed sections
- Preview results while generation continues

## Regenerating Audio

If you're not satisfied with a generated chunk:

1. Navigate to the chunk in the Project Editor
2. Optionally adjust settings (voice, speed, emotion, etc.)
3. Click **Regenerate** to create new audio for just that chunk

The section and chapter audio will be automatically re-rolled to include the new version.

## Next Steps

- [Audio Validation](./12-audio-validation) — Verify generated audio quality with STT-based similarity scoring
- [Export](./06-export) — Export your finished audiobook in various formats
- [Emotion & Prosody](./08-emotion-prosody) — Fine-tune emotional expression
- [Project Editor](./03-project-editor) — Navigate and edit your project
