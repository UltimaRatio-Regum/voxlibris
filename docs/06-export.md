---
title: Export
description: Export your audiobook as MP3, ZIP, or M4B with chapters
category: Audio
order: 6
keywords: [export, download, mp3, m4b, zip, chapters, audiobook format]
---

# Export

Once your audiobook audio is generated, you can export it in several formats.

## Export Formats

| Format | Description | Best For |
|--------|-------------|----------|
| **Single MP3** | One combined MP3 file | Simple playback, sharing |
| **MP3 per Chapter (ZIP)** | ZIP archive with one MP3 per chapter | Music players, manual organization |
| **M4B with Chapters** | M4B audiobook format with embedded chapter markers | Audiobook apps (Apple Books, etc.) |

## Starting an Export

1. Open your project in the **Project Editor**
2. Click the **Export** button in the audio section
3. Select your desired format
4. The export runs as a background job

## Export Jobs

Exports run as background jobs, just like audio generation:

- Monitor progress in the **Jobs** tab
- Export jobs show chapter-level progress (e.g., "Chapter 3 of 12")
- Jobs are labeled with the export format and project name

## Downloading

Once the export job completes:

- A download link appears in the **Jobs** panel
- The exported file is also available in the project's **Audio Files** list
- Click to download with the correct file extension and content type

## M4B Chapter Markers

When exporting as M4B:

- Chapter markers are embedded automatically based on your project's chapter structure
- Chapter titles are taken from your project's chapter names
- Compatible with most audiobook players (Apple Books, Libation, Prologue, etc.)

## Managing Export Files

Exported files appear in the project's audio files list with a scope of "export":

- View all exports for a project
- Download previous exports
- Delete exports you no longer need

## Tips

- Ensure all audio is generated before exporting — incomplete sections will result in gaps
- M4B is the recommended format for audiobook distribution
- Large projects may take several minutes to export as M4B
- You can start multiple exports in different formats simultaneously

## Next Steps

- [Audio Generation](./audio-generation) — Make sure all audio is generated first
- [Project Editor](./project-editor) — Review your project before export
