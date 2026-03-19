---
title: Speaker Detection & Assignment
description: How VoxLibris identifies speakers and how to manage assignments
category: Projects
order: 7
keywords: [speakers, dialogue, detection, assignment, characters, narrator, merge]
---

# Speaker Detection & Assignment

VoxLibris uses AI-powered analysis to identify who is speaking in your text. Understanding how this works helps you get better results.

## How Speaker Detection Works

The system uses five strategies to identify speakers:

### 1. Explicit Named Tags
Direct dialogue attribution like `"Hello," said John` or `Mary asked, "Where are we?"`. This is the most reliable method.

### 2. Multi-Word Speaker Names
Handles compound names like "Detective Chen" or "Professor Williams". The system normalizes these (e.g., "Detective Chen" → "Chen") for consistency.

### 3. Pronoun Resolution
When dialogue uses pronouns (`"Stop!" he shouted`), the system tracks:
- Gender context from surrounding text
- Previous speaker references
- Turn-taking patterns
- Same-speaker continuation cues

### 4. Narrative Context
Non-dialogue text (narration, descriptions) is attributed to the **Narrator** speaker.

### 5. Turn-Taking Inference
In rapid dialogue exchanges without explicit tags, the system alternates between the most recently identified speakers.

## Speaker Inspector

The **Speaker Inspector** (accessible from the Project Editor) provides tools to manage detected speakers:

### Viewing Speakers
- See all detected speakers with their chunk counts
- Preview sample text for each speaker
- Identify potential duplicates or misattributions

### Merging Speakers
If the AI created duplicate entries for the same character (e.g., "John" and "Mr. Smith" for the same person):

1. Open the Speaker Inspector
2. Select the speakers to merge
3. Choose the canonical name to keep
4. All chunks are reassigned to the merged speaker

### Reassigning Chunks
If a chunk was attributed to the wrong speaker:

1. Click on the chunk in the Project Editor
2. Change the speaker assignment from the dropdown
3. The chunk will use the new speaker's voice when regenerated

## Known Speakers

When creating a project, you can provide a list of known speaker names. The AI will preferentially match dialogue to these names, improving accuracy for:

- Sequels where you want consistent character names
- Stories with unusual character names
- Text where dialogue attribution is sparse

## Narrator Speaker

The narrator is a special speaker that represents non-dialogue text:

- Always present in every project
- Cannot be removed or merged
- Has its own voice assignment
- Covers narration, descriptions, scene-setting, etc.

## Emotion for Dialogue

Each chunk receives an emotion label regardless of speaker type. For dialogue:

- **Dialogue emotion flattening** can unify emotion across contiguous same-speaker dialogue chunks
- Two modes: **first-chunk** (use emotion of first chunk) or **word-count-majority** (use emotion from the chunk with the most words)
- Configure in [Settings](./settings)

## Tips for Better Detection

- Use clear dialogue tags (`said`, `asked`, `replied`) for best results
- Name characters consistently throughout the text
- Avoid ambiguous pronoun usage in rapid dialogue
- Provide known speakers list when available
- The editable parsing prompt in Settings can be customized for your content

## Next Steps

- [Emotion & Prosody](./emotion-prosody) — How emotions affect speech generation
- [Voice Selection](./voices) — Assign voices to detected speakers
- [Project Editor](./project-editor) — Edit speaker assignments in context
