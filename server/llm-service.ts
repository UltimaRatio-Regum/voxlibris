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

// Default to ChatGPT
export const DEFAULT_MODEL = "openai/gpt-5.4";

export interface SpeakerCandidates {
  [speaker: string]: number; // name -> confidence 0-1
}

export interface LLMSegment {
  type: "spoken" | "narration";
  text: string;
  speaker_candidates?: SpeakerCandidates;
  emotion?: {
    label: string;
    score: number;
  };
  sentiment?: {  // Legacy fallback
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

// Check if speaker confidence has low variance (needs manual review)
function needsReview(candidates: SpeakerCandidates | undefined): boolean {
  if (!candidates) return false;
  const scores = Object.values(candidates);
  if (scores.length < 2) return false;
  
  // Sort descending
  scores.sort((a, b) => b - a);
  const topScore = scores[0];
  const secondScore = scores[1];
  
  // If difference between top two is less than 0.3, needs review
  return (topScore - secondScore) < 0.3;
}

// Get the most likely speaker from candidates
function getMostLikelySpeaker(candidates: SpeakerCandidates | undefined): string | null {
  if (!candidates) return null;
  const entries = Object.entries(candidates);
  if (entries.length === 0) return null;
  
  entries.sort((a, b) => b[1] - a[1]);
  return entries[0][0];
}

// Convert LLM result to our segment format
function convertLLMResult(result: LLMParseResult): ParsedTextResult {
  const segments: SpeakerSegment[] = [];
  
  for (const chunk of result.chunks) {
    for (const seg of chunk.segments) {
      const isSpoken = seg.type === "spoken";
      const candidates = isSpoken ? seg.speaker_candidates : null;
      
      segments.push({
        text: seg.text,
        type: isSpoken ? "dialogue" : "narration",
        speaker: isSpoken ? getMostLikelySpeaker(candidates ?? undefined) : null,
        speakerCandidates: candidates ?? null,
        needsReview: needsReview(candidates ?? undefined),
        sentiment: seg.emotion ?? seg.sentiment ?? null,
        chunkId: chunk.chunk_id,
        approxDurationSeconds: chunk.approx_duration_seconds,
      });
    }
  }
  
  return {
    segments,
    detectedSpeakers: result.characters || [],
  };
}

// Split text into ~2-3 paragraph batches for better progress tracking
// Avoids splitting mid-dialogue by looking for safe break points
function splitIntoParagraphBatches(text: string, paragraphsPerBatch: number = 3): string[] {
  // Split by double newlines (paragraphs)
  const paragraphs = text.split(/\n\n+/).filter(p => p.trim().length > 0);
  
  if (paragraphs.length === 0) {
    return text.trim() ? [text] : [];
  }
  
  const batches: string[] = [];
  let currentBatch: string[] = [];
  let straightQuoteCount = 0;  // Straight quotes toggle (odd = open, even = closed)
  let curlyQuoteBalance = 0;   // Curly quotes have distinct open/close
  
  for (let i = 0; i < paragraphs.length; i++) {
    const para = paragraphs[i];
    currentBatch.push(para);
    
    // Count straight quotes (these toggle between open/close)
    const straightQuotes = (para.match(/"/g) || []).length;
    straightQuoteCount += straightQuotes;
    
    // Count curly quotes (distinct open/close)
    const curlyOpen = (para.match(/[\u201c]/g) || []).length;
    const curlyClose = (para.match(/[\u201d]/g) || []).length;
    curlyQuoteBalance += curlyOpen - curlyClose;
    
    // Check if we should finalize this batch
    const atBatchLimit = currentBatch.length >= paragraphsPerBatch;
    const isLastParagraph = i === paragraphs.length - 1;
    
    // Quotes are balanced if:
    // - Straight quote count is even (pairs closed)
    // - Curly quote balance is 0 or negative
    const straightQuotesBalanced = (straightQuoteCount % 2) === 0;
    const curlyQuotesBalanced = curlyQuoteBalance <= 0;
    const quotesBalanced = straightQuotesBalanced && curlyQuotesBalanced;
    
    // Prevent runaway batches: cap at 2x the target size
    const batchTooLarge = currentBatch.length >= paragraphsPerBatch * 2;
    
    // Only split if quotes are balanced (not mid-dialogue) or at end or batch too large
    if ((atBatchLimit && quotesBalanced) || isLastParagraph || batchTooLarge) {
      batches.push(currentBatch.join("\n\n"));
      currentBatch = [];
      straightQuoteCount = 0;
      curlyQuoteBalance = 0;
    }
  }
  
  // Handle any remaining paragraphs
  if (currentBatch.length > 0) {
    batches.push(currentBatch.join("\n\n"));
  }
  
  return batches.length > 0 ? batches : [text];
}

// Fixed set of emotions for consistent prosody adjustments
// Each emotion maps to specific pitch (+/-1%) and speed (+/-1%) adjustments
const VALID_EMOTIONS = [
  "neutral",    // No adjustment
  "happy",      // +1% pitch, +1% speed
  "sad",        // -1% pitch, -1% speed
  "angry",      // +1% pitch, +1% speed
  "fearful",    // +1% pitch, +1% speed
  "surprised",  // +1% pitch, +1% speed
  "disgusted",  // -1% pitch, -1% speed
  "excited",    // +1% pitch, +1% speed
  "calm",       // 0% pitch, -1% speed
  "anxious",    // +0.5% pitch, +1% speed
  "hopeful",    // +0.5% pitch, 0% speed
  "melancholy", // -0.5% pitch, -1% speed
] as const;

const SYSTEM_PROMPT = `You are an expert text analyzer for audiobook production. Your task is to parse narrative text into structured chunks suitable for audio generation.

Rules for chunking and segmentation:
1. Split text at natural stopping points into chunks of approximately 30 seconds of audio (roughly 75-100 words per chunk)
2. Each chunk should contain segments that are EITHER all narration OR a single speaker's dialogue
3. ALWAYS split at transitions between speaking and narrating
4. Text within quotation marks (straight " or curly "") is spoken dialogue
5. Text outside quotes is narration

For each segment:
- Identify the speaker from context clues (dialogue tags like "said John", or contextual inference) for spoken segments
- Provide confidence scores for each possible speaker (values 0-1, must sum to 1)
- Assign an emotion from this FIXED list ONLY: ${VALID_EMOTIONS.join(", ")}

EMOTION REFERENCE TABLE:
| Emotion    | Use When                                           |
|------------|---------------------------------------------------|
| neutral    | Default, factual narration, no strong emotion     |
| happy      | Joy, pleasure, satisfaction, positive outcomes    |
| sad        | Sorrow, disappointment, loss, grief               |
| angry      | Frustration, rage, annoyance, confrontation       |
| fearful    | Fear, worry, dread, danger, threat                |
| surprised  | Shock, astonishment, unexpected events            |
| disgusted  | Revulsion, disapproval, distaste                  |
| excited    | Enthusiasm, anticipation, energy, thrill          |
| calm       | Peaceful, serene, relaxed, reassuring             |
| anxious    | Nervousness, unease, tension, apprehension        |
| hopeful    | Optimism, anticipation of good, looking forward   |
| melancholy | Wistful sadness, nostalgia, bittersweet feelings  |

Return JSON in this exact format:
{
  "characters": ["Character Name 1", "Character Name 2"],
  "chunks": [
    {
      "chunk_id": 1,
      "approx_duration_seconds": 30,
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
- Preserve the EXACT text including quotation marks
- Include ALL text with no gaps
- Chunk IDs should be sequential starting from the provided starting ID
- Use context from previous exchanges to identify speakers consistently
- ONLY use emotions from the fixed list above - do not invent new emotion labels`;

// Parse text using conversational approach (maintaining context across batches)
async function parseWithConversation(
  text: string,
  model: string,
  knownSpeakers: string[]
): Promise<LLMParseResult> {
  const batches = splitIntoParagraphBatches(text, 3);
  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: "system", content: SYSTEM_PROMPT }
  ];
  
  // Add known speakers hint if provided
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
    const isLast = i === batches.length - 1;
    
    const userPrompt = isFirst
      ? `Parse the following text into chunks and segments. Start chunk IDs at ${nextChunkId}.\n\nHere is the text:\n\n${batch}`
      : `Continue parsing the next section. Continue chunk IDs from ${nextChunkId}. Use the same characters identified so far.\n\nHere is the text:\n\n${batch}`;
    
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
    
    // Add assistant response to conversation history
    messages.push({ role: "assistant", content });
    
    // Parse the response
    const parsed = JSON.parse(content) as LLMParseResult;
    
    // Collect characters
    if (parsed.characters) {
      parsed.characters.forEach(c => allCharacters.add(c));
    }
    
    // Collect chunks and update next chunk ID
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

// Streaming version that yields results batch by batch
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
  
  // Initial progress update
  yield { type: 'progress', chunkIndex: 0, totalChunks: totalBatches };
  
  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: "system", content: SYSTEM_PROMPT }
  ];
  
  // Add known speakers hint if provided
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
      ? `Parse the following text into chunks and segments. Start chunk IDs at ${nextChunkId}.\n\nHere is the text:\n\n${batch}`
      : `Continue parsing the next section. Continue chunk IDs from ${nextChunkId}. Use the same characters identified so far.\n\nHere is the text:\n\n${batch}`;
    
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
      
      // Add assistant response to conversation history for context
      messages.push({ role: "assistant", content });
      
      // Parse the response
      const parsed = JSON.parse(content) as LLMParseResult;
      
      // Collect characters
      if (parsed.characters) {
        parsed.characters.forEach(c => allCharacters.add(c));
      }
      
      // Convert to our segment format
      const batchSegments: SpeakerSegment[] = [];
      if (parsed.chunks && Array.isArray(parsed.chunks)) {
        for (const chunk of parsed.chunks) {
          if (chunk.chunk_id >= nextChunkId) {
            nextChunkId = chunk.chunk_id + 1;
          }
          
          for (const seg of chunk.segments) {
            const isSpoken = seg.type === "spoken";
            const candidates = isSpoken ? seg.speaker_candidates : null;
            
            batchSegments.push({
              text: seg.text,
              type: isSpoken ? "dialogue" : "narration",
              speaker: isSpoken ? getMostLikelySpeaker(candidates ?? undefined) : null,
              speakerCandidates: candidates ?? null,
              needsReview: needsReview(candidates ?? undefined),
              sentiment: seg.emotion ?? seg.sentiment ?? null,
              chunkId: chunk.chunk_id,
              approxDurationSeconds: chunk.approx_duration_seconds,
            });
          }
        }
      }
      
      // Yield this batch's results
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
  
  // Final completion update
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
