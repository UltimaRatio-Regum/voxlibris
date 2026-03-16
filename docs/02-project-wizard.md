---
title: Project Wizard
description: Step-by-step guide to creating audiobook projects with the wizard
category: Basics
order: 2
keywords: [wizard, create project, upload, text, epub, new project]
---

# Project Wizard

The Project Wizard guides you through creating a new audiobook project in four simple steps.

## Step 1: Upload

Start by providing the text you want to convert to an audiobook. You have several options:

### Paste Text
Type or paste your text directly into the text input area. This is ideal for short stories, articles, or excerpts.

### Upload a File
Click the upload area to select a file from your computer:

- **Text files (`.txt`)** — Plain text content is imported directly
- **EPUB files (`.epub`)** — Chapters are automatically extracted and organized

### Project Name
Give your project a meaningful name. If you upload a file, the filename is used as a default.

## Step 2: Analyzing

Once you submit your text, VoxLibris processes it automatically:

1. **Text segmentation** — The text is divided into logical sections
2. **Chunk creation** — Sections are split into audio-sized chunks (typically 8-12 seconds each)
3. **Speaker detection** — Dialogue is identified and attributed to characters using AI
4. **Emotion analysis** — Each chunk receives an emotion label (happy, sad, tense, etc.)

This process uses an LLM (language model) for intelligent analysis. You can monitor the progress as sections are processed.

### Speaker Detection Strategies

The AI uses several strategies to identify who is speaking:

- **Named dialogue tags** — `"Hello," said John` → assigns to "John"
- **Pronoun resolution** — Tracks gender and context to resolve "he said" / "she replied"
- **Turn-taking inference** — Alternating dialogue lines are attributed to alternating speakers
- **Narrative context** — Non-dialogue text is attributed to the narrator

## Step 3: Voice Selection

After analysis, you'll see all detected speakers and can assign a voice to each one:

### Single Voice Mode
Assign one voice for the entire project — good for articles or single-narrator content.

### Per-Speaker Mode
Assign different voices for each character and the narrator — ideal for fiction with dialogue.

### Available Voice Sources

| Source | Description |
|--------|-------------|
| **Edge TTS** | Microsoft Azure neural voices — many languages and styles |
| **Soprano** | Local TTS engine for ultra-fast generation |
| **Voice Library** | Pre-recorded VCTK voice samples for cloning |
| **Custom Voices** | Your own uploaded voice samples |
| **Remote Engines** | External TTS services you've configured |

You can preview any voice before assigning it.

## Step 4: Generate

Click **Generate** to start audio creation:

- The wizard creates a TTS generation job
- You'll see real-time progress as each chunk is generated
- Once started, you're automatically redirected to the **Project Editor**
- Monitor the job's progress in the **Jobs** tab

## Tips

- For best results with speaker detection, use text with clear dialogue tags
- EPUB files with proper chapter markup produce the best-organized projects
- You can always re-assign voices and regenerate specific sections later in the Project Editor
