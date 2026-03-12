import OpenAI from "openai";

export function isOpenRouterConfigured(): boolean {
  return !!(
    process.env.AI_INTEGRATIONS_OPENROUTER_BASE_URL &&
    process.env.AI_INTEGRATIONS_OPENROUTER_API_KEY
  );
}

const openrouter = new OpenAI({
  baseURL: process.env.AI_INTEGRATIONS_OPENROUTER_BASE_URL,
  apiKey: process.env.AI_INTEGRATIONS_OPENROUTER_API_KEY,
});

export const DEFAULT_MODEL = "openai/gpt-5.4";

export interface SpeakerCandidates {
  [speaker: string]: number;
}

export interface LLMSegment {
  type: "spoken" | "narration";
  text: string;
  speaker_candidates?: SpeakerCandidates;
  emotion?: {
    label: string;
    score: number;
  };
  sentiment?: {
    label: string;
    score: number;
  };
}

export interface LLMChunk {
  chunk_id: number;
  approx_duration_seconds: number;
  segments: LLMSegment[];
}

export interface LLMParseResult {
  characters: string[];
  chunks: LLMChunk[];
}

export interface SpeakerSegment {
  text: string;
  type: "dialogue" | "narration";
  speaker: string | null;
  speakerCandidates: SpeakerCandidates | null;
  needsReview: boolean;
  sentiment: { label: string; score: number } | null;
  chunkId: number;
  approxDurationSeconds: number;
}

export interface ParsedTextResult {
  segments: SpeakerSegment[];
  detectedSpeakers: string[];
}

function needsReview(candidates: SpeakerCandidates | undefined): boolean {
  if (!candidates) return false;
  const scores = Object.values(candidates);
  if (scores.length < 2) return false;
  
  scores.sort((a, b) => b - a);
  const topScore = scores[0];
  const secondScore = scores[1];
  
  return (topScore - secondScore) < 0.3;
}

function getMostLikelySpeaker(candidates: SpeakerCandidates | undefined): string | null {
  if (!candidates) return null;
  const entries = Object.entries(candidates);
  if (entries.length === 0) return null;
  
  entries.sort((a, b) => b[1] - a[1]);
  return entries[0][0];
}

const TARGET_CHUNK_WORDS = 25;
const MAX_CHUNK_WORDS = 40;

function rechunkSegmentText(text: string): string[] {
  const words = text.split(/\s+/).filter(w => w.length > 0);
  if (words.length <= MAX_CHUNK_WORDS) {
    return [text];
  }
  
  const chunks: string[] = [];
  let remaining = text.trim();
  
  while (remaining.trim()) {
    const wordCount = remaining.split(/\s+/).filter(w => w.length > 0).length;
    if (wordCount <= MAX_CHUNK_WORDS) {
      chunks.push(remaining.trim());
      break;
    }
    
    const targetCharPos = wordsToCharPos(remaining, TARGET_CHUNK_WORDS);
    let splitPos = findBestSplit(remaining, targetCharPos);
    
    if (splitPos <= 0 || splitPos >= remaining.length - 1) {
      splitPos = targetCharPos;
      const spacePos = remaining.lastIndexOf(' ', splitPos);
      if (spacePos > 0) {
        splitPos = spacePos;
      }
    }
    
    const chunk = remaining.substring(0, splitPos).trim();
    remaining = remaining.substring(splitPos).trim();
    
    if (chunk) {
      chunks.push(chunk);
    }
  }
  
  return chunks.length > 0 ? chunks : [text];
}

function wordsToCharPos(text: string, wordCount: number): number {
  const words = text.split(/\s+/).filter(w => w.length > 0);
  if (wordCount >= words.length) return text.length;
  
  let currentWord = 0;
  let inWord = false;
  for (let i = 0; i < text.length; i++) {
    const isSpace = /\s/.test(text[i]);
    if (isSpace && inWord) {
      currentWord++;
      inWord = false;
      if (currentWord >= wordCount) return i;
    } else if (!isSpace) {
      inWord = true;
    }
  }
  
  const avgChars = text.length / Math.max(1, words.length);
  return Math.floor(wordCount * avgChars);
}

function findBestSplit(text: string, targetPos: number): number {
  const searchStart = Math.max(0, targetPos - 100);
  const searchEnd = Math.min(text.length, targetPos + 50);
  const region = text.substring(searchStart, searchEnd);
  
  const patterns: [RegExp, 'last' | 'mid'][] = [
    [/[.!?]\s+/g, 'last'],
    [/[:;]\s+/g, 'mid'],
    [/,\s+/g, 'mid'],
  ];
  
  for (const [pattern, strategy] of patterns) {
    const matches: RegExpExecArray[] = [];
    let m;
    while ((m = pattern.exec(region)) !== null) {
      matches.push(m);
    }
    if (matches.length > 0) {
      const best = strategy === 'last'
        ? matches[matches.length - 1]
        : matches.reduce((a, b) => 
            Math.abs(a.index + a[0].length - region.length / 2) < Math.abs(b.index + b[0].length - region.length / 2) ? a : b
          );
      return searchStart + best.index + best[0].length;
    }
  }
  
  const conjPattern = /\s+(and|but|or|yet|so|for|nor|because|though|while)\s+/gi;
  const conjMatches: RegExpExecArray[] = [];
  let cm;
  while ((cm = conjPattern.exec(region)) !== null) {
    conjMatches.push(cm);
  }
  if (conjMatches.length > 0) {
    const best = conjMatches.reduce((a, b) =>
      Math.abs(a.index - region.length / 2) < Math.abs(b.index - region.length / 2) ? a : b
    );
    return searchStart + best.index;
  }
  
  const spacePattern = /\s+/g;
  const spaceMatches: RegExpExecArray[] = [];
  let sm;
  while ((sm = spacePattern.exec(region)) !== null) {
    spaceMatches.push(sm);
  }
  if (spaceMatches.length > 0) {
    const best = spaceMatches.reduce((a, b) =>
      Math.abs(a.index - region.length / 2) < Math.abs(b.index - region.length / 2) ? a : b
    );
    return searchStart + best.index;
  }
  
  return targetPos;
}

function normalizeEmotion(emotion: { label: string; score: number } | null | undefined): { label: string; score: number } | null {
  if (!emotion) return null;
  const validSet = new Set<string>(VALID_EMOTIONS);
  if (validSet.has(emotion.label)) return emotion;
  return { label: "neutral", score: emotion.score };
}

function convertLLMResult(result: LLMParseResult): ParsedTextResult {
  const segments: SpeakerSegment[] = [];
  
  for (const chunk of result.chunks) {
    for (const seg of chunk.segments) {
      const isSpoken = seg.type === "spoken";
      const candidates = isSpoken ? seg.speaker_candidates : null;
      const emotion = normalizeEmotion(seg.emotion ?? seg.sentiment ?? null);
      
      const subTexts = rechunkSegmentText(seg.text);
      for (const st of subTexts) {
        segments.push({
          text: st,
          type: isSpoken ? "dialogue" : "narration",
          speaker: isSpoken ? getMostLikelySpeaker(candidates ?? undefined) : null,
          speakerCandidates: candidates ?? null,
          needsReview: needsReview(candidates ?? undefined),
          sentiment: emotion,
          chunkId: chunk.chunk_id,
          approxDurationSeconds: Math.round(st.split(/\s+/).filter(w => w.length > 0).length / 2.5 * 10) / 10,
        });
      }
    }
  }
  
  return {
    segments,
    detectedSpeakers: result.characters || [],
  };
}

function splitIntoParagraphBatches(text: string, paragraphsPerBatch: number = 3): string[] {
  const paragraphs = text.split(/\n\n+/).filter(p => p.trim().length > 0);
  
  if (paragraphs.length === 0) {
    return text.trim() ? [text] : [];
  }
  
  const batches: string[] = [];
  let currentBatch: string[] = [];
  let straightQuoteCount = 0;
  let curlyQuoteBalance = 0;
  
  for (let i = 0; i < paragraphs.length; i++) {
    const para = paragraphs[i];
    currentBatch.push(para);
    
    const straightQuotes = (para.match(/"/g) || []).length;
    straightQuoteCount += straightQuotes;
    
    const curlyOpen = (para.match(/[\u201c]/g) || []).length;
    const curlyClose = (para.match(/[\u201d]/g) || []).length;
    curlyQuoteBalance += curlyOpen - curlyClose;
    
    const atBatchLimit = currentBatch.length >= paragraphsPerBatch;
    const isLastParagraph = i === paragraphs.length - 1;
    
    const straightQuotesBalanced = (straightQuoteCount % 2) === 0;
    const curlyQuotesBalanced = curlyQuoteBalance <= 0;
    const quotesBalanced = straightQuotesBalanced && curlyQuotesBalanced;
    
    const batchTooLarge = currentBatch.length >= paragraphsPerBatch * 2;
    
    if ((atBatchLimit && quotesBalanced) || isLastParagraph || batchTooLarge) {
      batches.push(currentBatch.join("\n\n"));
      currentBatch = [];
      straightQuoteCount = 0;
      curlyQuoteBalance = 0;
    }
  }
  
  if (currentBatch.length > 0) {
    batches.push(currentBatch.join("\n\n"));
  }
  
  return batches.length > 0 ? batches : [text];
}

const VALID_EMOTIONS = [
  "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
  "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
] as const;

const DEFAULT_SYSTEM_PROMPT = `You are chunking text for a text-to-speech audiobook engine. Each segment will be sent to a TTS engine as a separate audio clip, so segment size directly controls audio quality.

TARGET: Aim for segments of roughly 25 words (~10 seconds of speech). Segments may be shorter or up to ~40 words when needed. The most important rule is that every segment must break at a NATURAL PAUSE POINT — a place where a human reader would briefly pause.

NATURAL PAUSE PRIORITY — THIS IS THE MOST IMPORTANT RULE:
Always break segments at natural speech boundaries. A shorter or longer segment that ends at a natural pause is ALWAYS better than one that hits a word-count target but breaks mid-thought. Do NOT greedily pack words up to a limit — look ahead and choose the break point that sounds most natural when read aloud.

Preferred break points (best to worst):
1. Sentence boundaries (periods, question marks, exclamation marks)
2. Semicolons, colons, or em-dashes
3. Before conjunctions (and, but, or, so, yet, because, though, while)
4. Before prepositional phrases (in, on, at, with, from, to, through, across, etc.)
5. Commas

BAD vs GOOD example:
Given: "This is a short sentence. I'm going to ramble on and on noticing that this is a longer sentence and make sure that the sentence gets broken up at a bad spot instead of a more natural one."

BAD (greedy fill, breaks mid-phrase):
- Segment 1: "This is a short sentence. I'm going to ramble on and on noticing that this is a longer sentence and make sure that the sentence gets broken up at a bad"
- Segment 2: "spot instead of a more natural one."

GOOD (respects sentence boundary, even though Segment 1 is short):
- Segment 1: "This is a short sentence."
- Segment 2: "I'm going to ramble on and on noticing that this is a longer sentence and make sure that the sentence gets broken up at a bad spot instead of a more natural one."

ALSO GOOD (splits long sentence at a natural clause boundary):
- Segment 1: "This is a short sentence."
- Segment 2: "I'm going to ramble on and on noticing that this is a longer sentence"
- Segment 3: "and make sure that the sentence gets broken up at a bad spot instead of a more natural one."

SEGMENTATION RULES:
1. QUOTE BOUNDARIES: Quoted dialogue (straight " or curly \u201c\u201d) must always be its own segment, separate from surrounding narration. Never mix dialogue and narration in one segment.
2. NATURAL PAUSES FIRST: Always prefer breaking at natural pause points over hitting a word-count target. A 5-word segment that ends at a sentence boundary is better than a 25-word segment that breaks mid-clause.
3. SOFT SIZE GUIDE: Target ~25 words per segment. Segments under 10 words are fine if they are complete sentences or short dialogue. Segments up to ~40 words are acceptable if breaking earlier would split a natural phrase. Avoid segments over 40 words.
4. KEEP SENTENCES WHOLE: Never split a single sentence that is under 40 words. Keep it as one segment even if it exceeds the ~25 word target. The soft max exists specifically to avoid breaking sentences. For example, a 36-word sentence must stay as one segment — do NOT split it into a 22-word fragment and a 14-word fragment.
5. TRANSITIONS: ALWAYS split at transitions between speaking and narrating.
6. TYPE: Each segment is either "spoken" (dialogue in quotes) or "narration" (everything else).

SPEAKER IDENTIFICATION — CRITICAL:
You MUST identify a speaker for EVERY spoken segment. Never leave speaker_candidates empty or omit it. Use ALL available evidence to determine who is speaking:

1. EXPLICIT DIALOGUE TAGS: "said John", "Mary whispered", "he replied" — use the named character directly.
2. PRONOUN RESOLUTION: If the tag says "he said" or "she asked", look at the surrounding narration to determine which character "he" or "she" refers to. Assign that character as the speaker.
3. TURN-TAKING ORDER: In a conversation between two or more characters, speakers typically alternate. If Character A spoke last, the next quote is very likely Character B. Use this pattern.
4. NARRATIVE CONTEXT: If narration describes a character's actions or thoughts immediately before a quote (e.g., "John stepped forward. \\"Let's go.\\""), that character is almost certainly the speaker.
5. CONTENT AND TONE: What is said can indicate who is speaking — a character's known personality, role, or speech patterns can help identify them.
6. SCENE CONTEXT: Consider who is present in the scene. If only two characters are in a room, all dialogue must be between them.
7. BEST GUESS AT LOW CONFIDENCE: If you cannot determine the speaker with high confidence, you MUST still provide your best guess. A low-confidence identification (e.g., 0.4) is far better than no identification at all. Use "Unknown" only as an absolute last resort when there are zero contextual clues whatsoever.

Examples of speaker inference:
- "She turned to leave. \\"I'll be back,\\" she promised." → The speaker is whoever "she" refers to in context. Assign that character with high confidence.
- After a line from John: "\\"That's ridiculous!\\"" (no dialogue tag) → Likely the other character in the conversation (turn-taking). Assign with moderate confidence (0.6-0.7).
- "The doctor examined the chart. \\"We need to operate immediately.\\"" → The doctor is speaking (narrative context). Assign with high confidence.

EMOTION: Assign exactly one emotion per segment from this FIXED list ONLY: ${VALID_EMOTIONS.join(", ")}

| Emotion    | Use When                                           |
|------------|---------------------------------------------------|
| neutral    | Default, factual narration, no strong emotion     |
| happy      | Joy, pleasure, satisfaction, positive outcomes    |
| sad        | Sorrow, disappointment, loss, grief               |
| angry      | Frustration, rage, annoyance, confrontation       |
| fear       | Fear, worry, dread, danger, threat                |
| disgust    | Revulsion, disapproval, distaste                  |
| surprise   | Shock, astonishment, unexpected events            |
| excited    | Enthusiasm, anticipation, energy, thrill          |
| calm       | Peaceful, serene, relaxed, reassuring             |
| anxious    | Nervousness, unease, tension, apprehension        |
| hopeful    | Optimism, anticipation of good, looking forward   |
| melancholy | Wistful sadness, nostalgia, bittersweet feelings  |
| tender     | Gentle affection, warmth, intimacy, caring        |
| proud      | Achievement, dignity, self-assurance, satisfaction|

EXAMPLE — given: "She walked through the crowded marketplace, scanning the stalls for anything useful. The smell of fresh bread drifted from a nearby bakery, mixing with the sharp tang of fish from the harbor. \\"Looking for something specific?\\" the old merchant asked, leaning forward."

Correct output — 3 segments in 1 chunk, NOT 1 large segment:
- Segment 1 (narration, 13w): "She walked through the crowded marketplace, scanning the stalls for anything useful."
- Segment 2 (narration, 20w): "The smell of fresh bread drifted from a nearby bakery, mixing with the sharp tang of fish from the harbor."
- Segment 3 (spoken, 8w): "\\"Looking for something specific?\\" the old merchant asked, leaning forward." → speaker_candidates: {"the old merchant": 0.95}

Return JSON in this exact format:
{
  "characters": ["Character Name 1", "Character Name 2"],
  "chunks": [
    {
      "chunk_id": 1,
      "approx_duration_seconds": 10,
      "segments": [
        {
          "type": "spoken",
          "text": "The exact quoted text including quotes",
          "speaker_candidates": {"CharacterA": 0.9, "CharacterB": 0.1},
          "emotion": {"label": "happy", "score": 0.8}
        },
        {
          "type": "narration",
          "text": "The narration text",
          "emotion": {"label": "neutral", "score": 0.7}
        }
      ]
    }
  ]
}

Important:
- Preserve the EXACT text including quotation marks — do not paraphrase, summarize, or omit words
- Include ALL text with no gaps
- Chunk IDs should be sequential starting from the provided starting ID
- Use context from previous exchanges to identify speakers consistently
- ONLY use emotions from the fixed list above — do not invent new emotion labels
- EVERY spoken segment MUST have a non-empty speaker_candidates object — never omit it`;

let cachedResolvedPrompt: string | null = null;
let cachedPromptTimestamp: number = 0;
const PROMPT_CACHE_TTL_MS = 5000;

export function invalidatePromptCache(): void {
  cachedResolvedPrompt = null;
  cachedPromptTimestamp = 0;
}

async function getSystemPrompt(): Promise<string> {
  const now = Date.now();
  if (cachedResolvedPrompt !== null && (now - cachedPromptTimestamp) < PROMPT_CACHE_TTL_MS) {
    return cachedResolvedPrompt;
  }

  try {
    const resp = await fetch(`http://localhost:${process.env.PYTHON_PORT || 8000}/parsing-prompt`);
    if (resp.ok) {
      const data = await resp.json() as { prompt: string; isCustom: boolean };
      if (data.isCustom && data.prompt) {
        const resolved = data.prompt.replace(/\$\{VALID_EMOTIONS\}/g, VALID_EMOTIONS.join(", "));
        cachedResolvedPrompt = resolved;
        cachedPromptTimestamp = now;
        return resolved;
      }
    }
  } catch {
  }

  cachedResolvedPrompt = DEFAULT_SYSTEM_PROMPT;
  cachedPromptTimestamp = now;
  return DEFAULT_SYSTEM_PROMPT;
}

export function getDefaultSystemPrompt(): string {
  return DEFAULT_SYSTEM_PROMPT;
}

async function parseWithConversation(
  text: string,
  model: string,
  knownSpeakers: string[]
): Promise<LLMParseResult> {
  const batches = splitIntoParagraphBatches(text, 3);
  const systemPrompt = await getSystemPrompt();
  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: "system", content: systemPrompt }
  ];
  
  if (knownSpeakers.length > 0) {
    messages.push({
      role: "user",
      content: `Known characters in this text: ${knownSpeakers.join(", ")}. Please use these names when identifying speakers.`
    });
    messages.push({
      role: "assistant",
      content: `Understood. I'll identify speakers using these character names: ${knownSpeakers.join(", ")}.`
    });
  }
  
  const allCharacters = new Set<string>(knownSpeakers);
  const allChunks: LLMChunk[] = [];
  let nextChunkId = 1;
  
  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    const isFirst = i === 0;
    
    const userPrompt = isFirst
      ? `Parse the following text into chunks and segments. Target ~25 words per segment (soft max ~40), but always break at natural pause points — never mid-phrase. Never split a single sentence that is under 40 words — keep it as one segment. Start chunk IDs at ${nextChunkId}.\n\nHere is the text:\n\n${batch}`
      : `Continue parsing the next section. Target ~25 words per segment (soft max ~40), but always break at natural pause points — never mid-phrase. Never split a single sentence that is under 40 words — keep it as one segment. Continue chunk IDs from ${nextChunkId}. Use the same characters identified so far.\n\nHere is the text:\n\n${batch}`;
    
    messages.push({ role: "user", content: userPrompt });
    
    const response = await openrouter.chat.completions.create({
      model,
      messages,
      max_tokens: 8192,
      temperature: 0.1,
      response_format: { type: "json_object" },
    });
    
    const content = response.choices[0]?.message?.content;
    if (!content) {
      throw new Error(`No response from LLM for batch ${i + 1}`);
    }
    
    messages.push({ role: "assistant", content });
    
    const parsed = JSON.parse(content) as LLMParseResult;
    
    if (parsed.characters) {
      parsed.characters.forEach(c => allCharacters.add(c));
    }
    
    if (parsed.chunks && Array.isArray(parsed.chunks)) {
      for (const chunk of parsed.chunks) {
        allChunks.push(chunk);
        if (chunk.chunk_id >= nextChunkId) {
          nextChunkId = chunk.chunk_id + 1;
        }
      }
    }
  }
  
  return {
    characters: Array.from(allCharacters),
    chunks: allChunks,
  };
}

export async function parseTextWithLLM(
  text: string,
  model: string = DEFAULT_MODEL,
  knownSpeakers: string[] = []
): Promise<ParsedTextResult> {
  if (!isOpenRouterConfigured()) {
    throw new Error("OpenRouter is not configured");
  }
  
  const result = await parseWithConversation(text, model, knownSpeakers);
  return convertLLMResult(result);
}

export interface StreamingParseUpdate {
  type: 'progress' | 'chunk' | 'complete' | 'error';
  chunkIndex?: number;
  totalChunks?: number;
  segments?: SpeakerSegment[];
  detectedSpeakers?: string[];
  error?: string;
}

export async function* parseTextWithLLMStreaming(
  text: string,
  model: string = DEFAULT_MODEL,
  knownSpeakers: string[] = []
): AsyncGenerator<StreamingParseUpdate> {
  if (!isOpenRouterConfigured()) {
    yield { type: 'error', error: 'OpenRouter is not configured' };
    return;
  }

  const batches = splitIntoParagraphBatches(text, 3);
  const totalBatches = batches.length;
  
  yield { type: 'progress', chunkIndex: 0, totalChunks: totalBatches };
  
  const systemPrompt = await getSystemPrompt();
  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: "system", content: systemPrompt }
  ];
  
  if (knownSpeakers.length > 0) {
    messages.push({
      role: "user",
      content: `Known characters in this text: ${knownSpeakers.join(", ")}. Please use these names when identifying speakers.`
    });
    messages.push({
      role: "assistant",
      content: `Understood. I'll identify speakers using these character names: ${knownSpeakers.join(", ")}.`
    });
  }
  
  const allCharacters = new Set<string>(knownSpeakers);
  let nextChunkId = 1;
  
  for (let i = 0; i < batches.length; i++) {
    const batch = batches[i];
    const isFirst = i === 0;
    
    const userPrompt = isFirst
      ? `Parse the following text into chunks and segments. Target ~25 words per segment (soft max ~40), but always break at natural pause points — never mid-phrase. Never split a single sentence that is under 40 words — keep it as one segment. Start chunk IDs at ${nextChunkId}.\n\nHere is the text:\n\n${batch}`
      : `Continue parsing the next section. Target ~25 words per segment (soft max ~40), but always break at natural pause points — never mid-phrase. Never split a single sentence that is under 40 words — keep it as one segment. Continue chunk IDs from ${nextChunkId}. Use the same characters identified so far.\n\nHere is the text:\n\n${batch}`;
    
    messages.push({ role: "user", content: userPrompt });
    
    try {
      const response = await openrouter.chat.completions.create({
        model,
        messages,
        max_tokens: 8192,
        temperature: 0.1,
        response_format: { type: "json_object" },
      });
      
      const content = response.choices[0]?.message?.content;
      if (!content) {
        throw new Error(`No response from LLM for batch ${i + 1}`);
      }
      
      messages.push({ role: "assistant", content });
      
      const parsed = JSON.parse(content) as LLMParseResult;
      
      if (parsed.characters) {
        parsed.characters.forEach(c => allCharacters.add(c));
      }
      
      const batchSegments: SpeakerSegment[] = [];
      if (parsed.chunks && Array.isArray(parsed.chunks)) {
        for (const chunk of parsed.chunks) {
          if (chunk.chunk_id >= nextChunkId) {
            nextChunkId = chunk.chunk_id + 1;
          }
          
          for (const seg of chunk.segments) {
            const isSpoken = seg.type === "spoken";
            const candidates = isSpoken ? seg.speaker_candidates : null;
            const emotion = normalizeEmotion(seg.emotion ?? seg.sentiment ?? null);
            
            const subTexts = rechunkSegmentText(seg.text);
            for (const st of subTexts) {
              batchSegments.push({
                text: st,
                type: isSpoken ? "dialogue" : "narration",
                speaker: isSpoken ? getMostLikelySpeaker(candidates ?? undefined) : null,
                speakerCandidates: candidates ?? null,
                needsReview: needsReview(candidates ?? undefined),
                sentiment: emotion,
                chunkId: chunk.chunk_id,
                approxDurationSeconds: Math.round(st.split(/\s+/).filter(w => w.length > 0).length / 2.5 * 10) / 10,
              });
            }
          }
        }
      }
      
      yield {
        type: 'chunk',
        chunkIndex: i + 1,
        totalChunks: totalBatches,
        segments: batchSegments,
        detectedSpeakers: Array.from(allCharacters),
      };
      
    } catch (error) {
      yield { 
        type: 'error', 
        error: error instanceof Error ? error.message : 'Unknown error',
        chunkIndex: i + 1,
        totalChunks: totalBatches
      };
      return;
    }
  }
  
  yield { 
    type: 'complete',
    chunkIndex: totalBatches,
    totalChunks: totalBatches,
    detectedSpeakers: Array.from(allCharacters)
  };
}

export async function getAvailableModels(): Promise<string[]> {
  return [
    "openai/gpt-5.4",
    "openai/gpt-5.3",
    "openai/gpt-4.1",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1-nano",
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "deepseek/deepseek-chat",
  ];
}

export { openrouter };
