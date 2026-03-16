---
title: Emotion & Prosody
description: Configure how emotions influence speech expressiveness
category: Audio
order: 8
keywords: [emotion, prosody, sentiment, expression, weights, narrator, dialogue]
---

# Emotion & Prosody

VoxLibris uses emotion analysis to make generated speech more expressive. Each text chunk is assigned an emotion that influences how the TTS engine renders the audio.

## Emotion Detection

During text analysis, the system assigns one of 14 canonical emotions to each chunk:

| Emotion | Typical Use |
|---------|-------------|
| Neutral | Default narration, factual statements |
| Happy | Joyful moments, good news |
| Sad | Loss, melancholy, disappointment |
| Angry | Confrontation, frustration |
| Fearful | Danger, anxiety, suspense |
| Surprised | Unexpected events, revelations |
| Disgusted | Revulsion, strong disapproval |
| Contemptuous | Disdain, arrogance |
| Tender | Affection, intimacy, gentleness |
| Excited | High energy, enthusiasm |
| Tense | Suspense, anticipation |
| Amused | Humor, light-heartedness |
| Bored | Monotony, disinterest |
| Calm | Peaceful, meditative passages |

### Detection Methods
- **Primary:** LLM-based analysis considers context, dialogue, and narrative cues
- **Fallback:** TextBlob sentiment analysis provides basic positive/negative/neutral labeling when LLM is unavailable

## Prosody Weights

Prosody weights control how strongly each emotion affects the generated speech. Configure these in **Settings** → **Emotion Prosody Weights**:

- **Higher weight** = more dramatic expression for that emotion
- **Lower weight** = subtler, more restrained expression
- **Zero weight** = emotion has no effect on speech

Adjust weights to match your content's tone:
- **Dramatic fiction** → Higher weights for angry, fearful, excited
- **Children's stories** → Higher weights for happy, surprised, amused
- **Non-fiction** → Lower weights overall for a measured delivery

## Narrator Emotion Override

For narration text, you can force a single emotion regardless of what the AI detected:

- Go to **Settings** or project settings
- Set the **Narrator Emotion Override** to your desired emotion
- All narration chunks will use this emotion instead of the detected one
- Useful for maintaining a consistent narrator tone throughout the book

## Dialogue Emotion Flattening

When a character speaks across multiple contiguous chunks, the emotion can vary between chunks. Flattening unifies the emotion:

### First-Chunk Mode
Uses the emotion from the first chunk in the contiguous sequence. Good for:
- Opening emotional tone that carries through
- Simple, predictable behavior

### Word-Count-Majority Mode
Uses the emotion from the chunk with the most words. Good for:
- Letting the dominant emotional content drive the tone
- More nuanced handling of longer speeches

## How Engines Use Emotions

Different TTS engines handle emotions differently:

- **Edge TTS** — Uses SSML emotion tags where available; some voices support built-in styles
- **Chatterbox** — Has an exaggeration parameter for emotion intensity
- **Other engines** — May use emotion-specific prompting or prosody modification

The **exaggeration** parameter (available in generation settings) controls how dramatically the engine expresses the detected emotion.

## Next Steps

- [Voice Selection](./voices) — Choose voices that support emotional expression
- [Settings](./settings) — Configure prosody weights and emotion defaults
- [Audio Generation](./audio-generation) — Generate expressive audio
