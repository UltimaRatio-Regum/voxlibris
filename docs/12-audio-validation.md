---
title: Audio Validation
description: Verify generated audio quality using STT-based similarity scoring, review flagged chunks, and queue targeted regeneration
category: Audio
order: 12
keywords: [validation, STT, speech-to-text, similarity, quality, flagged, regenerate, phonetic]
---

# Audio Validation

Audio Validation is a quality-assurance pipeline that listens to every generated chunk, transcribes it with a speech-to-text (STT) model, and compares the transcript to the source text using fuzzy-matching algorithms. Chunks that fall below a configurable similarity threshold are flagged for review or automatic regeneration.

## Accessing Validation

The **Validation** node appears in the Project Tree between the Output Files section and the Book Content tree. Click it to open the validation configuration and results panel. Once a validation run has completed, flagged chunks appear as child nodes under Validation — click any of them to inspect the individual result.

## Configuring a Validation Run

All settings are saved per-project, so your choices are pre-selected on every subsequent run.

### STT Model

Enter any multimodal model available via OpenRouter that accepts audio input. The default is `google/gemini-2.5-flash`. The model receives the raw WAV audio for each chunk and returns a verbatim transcript.

### Similarity Algorithms

Choose one or more algorithms to score how closely the transcript matches the source text. All scores are normalised to **0.0 (completely different) → 1.0 (identical)**.

| Algorithm | Description |
|-----------|-------------|
| **SequenceMatcher** | Python difflib character-level similarity |
| **Levenshtein** | Normalised edit distance |
| **Token Sort** | Order-invariant word comparison |
| **Jaro-Winkler** | Prefix-weighted character match |
| **WER Similarity** | `1 − Word Error Rate` |

### Phonetic Preprocessing

Enable **Phonetic Preprocessing (Double Metaphone)** to convert both the source text and the STT transcript into phonetic codes before any comparison is run. Each word is encoded independently so word-boundary algorithms (WER, Token Sort) continue to work correctly.

This is useful when a TTS engine mispronounces a word but the STT model transcribes what it hears correctly — the word *sounds* right even though the spelling differs. Phonetic preprocessing catches those cases that character-level algorithms would miss.

### Combining Multiple Scores

When more than one algorithm is selected, choose how the individual scores are combined into a single **combined score**:

| Method | Description |
|--------|-------------|
| **Average Similarity** | Mean of all scores |
| **Max Similarity** | Highest individual score |
| **Min Similarity** | Lowest individual score (strictest) |

**Drop Worst N** — before combining, discard the N lowest-scoring algorithms. For example, with 5 algorithms and Drop Worst 1, the single outlier is ignored and the remaining 4 are averaged. Use this to prevent one noisy algorithm from dragging down an otherwise-good result.

### Similarity Cutoff

Chunks with a combined score below this threshold are flagged. The default is **0.80** (80% similarity). Set it lower to flag only badly garbled audio; set it higher to catch subtle mispronunciations.

### Auto-Regenerate

When enabled, every flagged chunk is automatically queued for TTS re-generation immediately after the validation job finishes. This is off by default — it is best to run a test first, review the flagged results, and tune the cutoff before turning on automatic regeneration.

## Running Validation

Click **Start Validation** to submit the job. Validation runs in the background as a dedicated job type. A progress bar and percentage indicator appear while it is running.

The job:
1. Collects all chunks that have generated audio
2. Sends each chunk's audio to the configured STT model
3. Computes similarity scores against the source text
4. Flags any chunk whose combined score is below the cutoff
5. Optionally queues flagged chunks for regeneration (if Auto-Regenerate is on)

> **Tip:** Validation submits one STT call per chunk. For large projects this can take a few minutes and will consume OpenRouter credits proportional to your chunk count.

## Reviewing Results

After the job completes, the Validation panel shows a summary: how many chunks were validated and how many were flagged. Flagged chunks (that haven't already been regenerated) appear as expandable nodes in the Project Tree under **Validation**.

### Per-Chunk Detail

Click a flagged chunk node to open its detail view:

- **Source Text** — the original text the chunk was generated from
- **STT Transcript** — what the STT model heard
- **Algorithm Scores** — individual score for each algorithm that was run, colour-coded (red below 70%)
- **Generated Audio** — play the chunk directly from the detail panel
- **Combined Score** badge — the final aggregated score

### Actions on a Flagged Chunk

| Button | Effect |
|--------|--------|
| **Mark as Good** | Removes the flag; the chunk is considered acceptable and disappears from the Validation tree |
| **Regenerate Chunk** | Queues the chunk for a new TTS generation pass and marks it as regenerated so it no longer appears in the flagged list |

## Batch Actions

From the main Validation panel:

- **Apply Changes** — Re-evaluates all previously collected STT results against the current algorithm/cutoff settings *without* running STT again. Use this to experiment with different cutoff values or algorithm combinations after the initial run.
- **Regenerate All Flagged (`N`)** — Queues every currently-flagged, non-regenerated chunk for TTS re-generation in one click. If you have already removed some from the list with Mark as Good, only the remaining flagged chunks are submitted.

## Iterative Workflow

A typical workflow for a new project:

1. Generate all audio for the project
2. Open Validation, leave Auto-Regenerate **off**
3. Start Validation with the default settings
4. When it completes, review the flagged chunks — listen to the audio and read the transcripts
5. If the cutoff feels too strict or too lenient, adjust it and click **Apply Changes** to re-flag without re-running STT
6. Once you are satisfied with the cutoff, click **Regenerate All Flagged** (or enable Auto-Regenerate for future runs)
7. After regeneration completes, run validation again to confirm the re-generated chunks pass

## Next Steps

- [Audio Generation](./05-audio-generation) — Generate audio before running validation
- [Export](./06-export) — Export your finished audiobook
- [Project Editor](./03-project-editor) — Navigate chapters, sections, and chunks
