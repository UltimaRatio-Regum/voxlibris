---
title: Tips & Shortcuts
description: Productivity tips, best practices, and workflow shortcuts
category: Reference
order: 11
keywords: [tips, shortcuts, best practices, workflow, productivity]
---

# Tips & Shortcuts

Get the most out of VoxLibris with these tips and best practices.

## Text Preparation

### For Best Speaker Detection
- Use clear dialogue tags: `"Hello," said John.` works better than `"Hello." John looked up.`
- Be consistent with character names — pick one name per character and stick with it
- Avoid starting dialogue with pronouns when the speaker isn't obvious

### For Best Chunking
- Use paragraph breaks to separate logical sections
- Scene breaks (blank lines, `***`, or `---`) help the chunker identify section boundaries
- Chapters should be clearly marked in EPUB files

### EPUB Files
- Well-structured EPUBs produce the best results
- Chapters are automatically extracted as separate chapters in the project
- Metadata (title, author) is imported when available

## Voice Selection Tips

### Matching Voices to Characters
- Use **deep, slower voices** for older or authoritative characters
- Use **lighter, faster voices** for younger characters
- Use a **consistent, neutral voice** for the narrator
- Preview multiple options before committing

### Custom Voice Recordings
- Record in a quiet environment with minimal background noise
- Speak naturally — don't try to "perform" unless that's the desired effect
- 10-20 seconds of clean speech is ideal for most cloning engines
- Include a text transcript for better cloning results

## Generation Workflow

### Efficient Workflows
1. **Start with the Wizard** for new projects — it handles setup automatically
2. **Review the project tree** before generating — fix speaker assignments first
3. **Generate in sections** for long texts — easier to review and regenerate specific parts
4. **Use Soprano for previews** — it's the fastest engine for quick checks
5. **Switch to Edge TTS or remote engines** for final quality

### Regenerating Specific Parts
- Navigate to the specific chunk in the Project Editor
- Adjust settings if needed (voice, emotion, speed)
- Regenerate just that chunk — much faster than regenerating the whole project
- Section and chapter audio will automatically update

## Export Best Practices

### Choosing a Format
- **M4B** is the gold standard for audiobooks — supports chapter markers
- **ZIP with MP3s** is good for manual organization or custom players
- **Single MP3** works for short content or simple playback

### Before Exporting
- Check that all sections have generated audio
- Review any sections marked with warnings
- Listen to a few samples from different chapters to verify quality

## Troubleshooting

### Audio Quality Issues
- Try a different TTS engine or voice
- Adjust the speed — some voices sound better slightly slower or faster
- Check the emotion assignment — an incorrect emotion can produce odd prosody
- For cloned voices, try a longer or cleaner voice sample

### Speaker Detection Problems
- Use the Speaker Inspector to merge duplicate speakers
- Manually reassign chunks that were attributed to the wrong speaker
- Edit the parsing prompt in Settings to add rules for your content's style
- Re-chunk sections where detection was particularly poor

### Remote Engine Issues
- Check that the engine endpoint is accessible
- Allow time for cold-start warm-up (especially for HuggingFace Spaces)
- Verify the engine supports the features you need (voice cloning, emotions, etc.)
- Check the engine status indicator in Settings

## Performance Tips

- **Parallel generation** — Jobs process sections in parallel for faster completion
- **Preview with fast engines** — Use Soprano for quick previews, then switch to higher-quality engines
- **Incremental generation** — Generate chapter by chapter rather than the entire book at once
- **Re-chunk sparingly** — Only re-chunk sections where the original chunking is problematic
