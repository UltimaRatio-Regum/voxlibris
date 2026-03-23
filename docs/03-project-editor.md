---
title: Project Editor
description: Navigate and edit the chapter/section/chunk hierarchy of your audiobook
category: Projects
order: 3
keywords: [editor, chapters, sections, chunks, hierarchy, project, edit, tree]
---

# Project Editor

The Project Editor is where you fine-tune your audiobook. It provides a hierarchical view of your content organized as **Book → Chapters → Sections → Chunks**.

## Content Hierarchy

| Level | Description |
|-------|-------------|
| **Book** | The entire audiobook project |
| **Chapter** | Major divisions (from EPUB chapters or manual splits) |
| **Section** | Logical groupings within chapters (scenes, passages) |
| **Chunk** | Individual audio segments (8-12 seconds each) |

The tree also contains two special nodes below the project root:

- **Output Files** — exported audiobook files
- **Validation** — audio quality validation results (see [Audio Validation](./12-audio-validation))

## Two-Panel Layout

The editor uses a two-panel layout:

### Left Panel — Project Tree
A collapsible tree view showing the full hierarchy. Click any node to select it and view its details.

### Right Panel — Detail View
Shows the details of the selected item, including:

- **Text content** of the selected chunk, section, or chapter
- **Speaker assignment** for individual chunks
- **Emotion labels** assigned by the AI
- **Audio playback** for generated segments
- **Settings overrides** at any level

## Working with Sections

Each section contains a group of related chunks. In the section detail panel you can:

- View all chunks in the section
- Play generated audio for the section
- **Re-chunk** the section — splits the text again using the AI, useful if the original chunking wasn't optimal
  - Choose which LLM model to use for re-chunking
  - The raw text is preserved and re-processed

## Working with Chunks

Individual chunks are the smallest editable units. For each chunk you can:

- See the text and its assigned speaker
- View and change the emotion label
- Listen to generated audio
- Override voice or engine settings
- Regenerate audio for just that chunk

## Settings Overrides

You can override default settings at any level of the hierarchy:

- **Book level** — Default settings for the entire project
- **Chapter level** — Override for all sections in that chapter
- **Section level** — Override for all chunks in that section
- **Chunk level** — Override for a specific chunk only

Overrides cascade downward: a chapter override applies to all its sections and chunks unless they have their own override.

## Audio Playback

Generated audio is available at multiple levels:

- **Chunk** — Play individual segments
- **Section** — Combined audio for all chunks in the section
- **Chapter** — Combined audio for all sections in the chapter

Audio is rolled up automatically: chunk audio is combined into section audio, and section audio into chapter audio.

## Project Metadata

Click the project name or settings icon to edit metadata:

- **Title** and **Author**
- **Cover image** — Upload a cover for M4B exports
- **Description** and other metadata fields

## Re-segmentation

If the original AI chunking wasn't optimal you can re-segment the project from the project-level detail panel:

- Choose a different **Analysis Model** for the re-segmentation pass
- **Merge short / punctuation-only chunks** — automatically combines the result of the merge pass (see below) immediately after segmentation finishes. On by default.
- Click **Re-segment** to discard all existing sections and chunks and re-process the source text

## Chunk Merging

The **Merge Short Chunks** button runs a post-processing pass on the *existing* segmentation without calling the AI again. It:

1. Runs three sweeps through every section, joining punctuation-only chunks and chunks of three words or fewer into an adjacent chunk that shares the same speaker
2. After the three sweeps, deletes any remaining punctuation-only chunks that had no matching neighbour
3. Removes any sections that are left empty after deletion

This is useful for cleaning up artefacts without a full re-segment. The button reports how many chunks were eliminated.

You can also enable the merge pass as part of an initial segmentation or re-segmentation by ticking the **Merge short / punctuation-only chunks** checkbox in the Re-segment section.

## Next Steps

- [Audio Generation](./05-audio-generation) — Learn about generating and managing audio
- [Audio Validation](./12-audio-validation) — Verify generated audio quality
- [Speaker Detection](./07-speaker-detection) — Understand how speakers are identified
- [Export](./06-export) — Export your finished audiobook
