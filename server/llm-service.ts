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

export interface SpeakerSegment {
  text: string;
  type: "dialogue" | "narration";
  speaker: string | null;
}

export interface ParsedTextResult {
  segments: SpeakerSegment[];
  detectedSpeakers: string[];
}

// Common words that look like names but aren't (expanded list)
const NON_NAME_WORDS = new Set([
  // Pronouns and articles
  "I", "A", "The", "It", "He", "She", "They", "We", "You", "My", "Your", "His", "Her",
  "Their", "Our", "This", "That", "These", "Those", "What", "Where", "When", "Why",
  "How", "Who", "Which", "Its", "One", "Some", "Any", "Each", "Every", "All", "Both",
  // Conjunctions and prepositions
  "If", "But", "And", "Or", "So", "Yet", "For", "Nor", "As", "At", "By", "In", "On",
  "To", "Up", "Of", "With", "From", "Into", "Over", "Under", "After", "Before",
  // Common words often capitalized
  "Oh", "Ah", "Yes", "No", "Well", "Now", "Then", "Here", "There", "Today",
  "Tomorrow", "Yesterday", "Perhaps", "Maybe", "Please", "Thanks", "Sorry",
  // Days and months
  "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
  "January", "February", "March", "April", "May", "June", "July", "August",
  "September", "October", "November", "December",
  // Titles
  "Mr", "Mrs", "Ms", "Dr", "Prof", "Sir", "Lord", "Lady", "Captain", "General",
  "Colonel", "King", "Queen", "Prince", "Princess", "Duke", "Duchess", "Earl",
  // Document structure
  "Chapter", "Part", "Book", "Volume", "Section", "Page", "Note", "Figure",
  "Table", "Appendix", "Index", "Prologue", "Epilogue", "Introduction",
  // Common nouns often capitalized in fiction
  "Father", "Mother", "Brother", "Sister", "Uncle", "Aunt", "Grandmother",
  "Grandfather", "God", "Heaven", "Hell", "Earth", "World", "Universe",
  // Places and concepts
  "North", "South", "East", "West", "City", "Town", "Country", "State",
  "Street", "Avenue", "Road", "Building", "House", "Room", "Door", "Window",
]);

// Extract potential character names from text using proper noun detection
export function extractPotentialNames(text: string): string[] {
  const names = new Set<string>();
  
  // Pattern for capitalized words that might be names
  // Look for: word starting with capital followed by lowercase, not at sentence start
  const patterns = [
    // Names after dialogue verbs: said John, replied Mary
    /(?:said|asked|replied|answered|whispered|shouted|exclaimed|murmured|muttered|called|cried|yelled|screamed|announced|declared|demanded|insisted|suggested|wondered|thought|mused)\s+([A-Z][a-z]+)/gi,
    // Names before dialogue verbs: John said, Mary replied
    /([A-Z][a-z]+)\s+(?:said|asked|replied|answered|whispered|shouted|exclaimed|murmured|muttered|called|cried|yelled|screamed|announced|declared|demanded|insisted|suggested|wondered|thought|mused)/gi,
    // Names after pronouns indicating action: "Hello," John said
    /["""][^"""]+["""]\s+([A-Z][a-z]+)\s+/g,
    // Two capitalized words together (first + last name): John Smith, Mary Jane
    /\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b/g,
    // Standalone capitalized words mid-sentence (after lowercase word)
    /[a-z.,!?]\s+([A-Z][a-z]{2,})\b/g,
  ];

  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(text)) !== null) {
      // Handle single or multiple capture groups
      for (let i = 1; i < match.length; i++) {
        const name = match[i];
        if (name && name.length >= 2 && !NON_NAME_WORDS.has(name)) {
          names.add(name);
        }
      }
    }
  }

  return Array.from(names);
}

// Check if a position is inside an open quote (from startPos to position)
// Supports double quotes (straight and curly) and single quotes
function isInsideQuote(text: string, startPos: number, position: number): boolean {
  let doubleQuoteCount = 0;
  let singleQuoteCount = 0;
  
  for (let i = startPos; i < position && i < text.length; i++) {
    const char = text[i];
    // Handle straight and curly double quotes
    if (char === '"' || char === '\u201c' || char === '\u201d') {
      doubleQuoteCount++;
    }
    // Handle straight and curly single quotes (apostrophe-like)
    if (char === "'" || char === '\u2018' || char === '\u2019') {
      // Only count as dialogue quote if not preceded by a letter (avoids contractions like "don't")
      if (i === startPos || !/[a-zA-Z]/.test(text[i - 1])) {
        singleQuoteCount++;
      }
    }
  }
  
  // Inside quote if either type has odd count
  return doubleQuoteCount % 2 === 1 || singleQuoteCount % 2 === 1;
}

// Find a safe split point that doesn't break quotes
function findSafeSplitPoint(text: string, startPos: number, targetEnd: number): number {
  const minPos = startPos + Math.floor((targetEnd - startPos) * 0.3);
  
  // Look for paragraph break first (safest)
  for (let i = targetEnd; i >= minPos; i--) {
    if (i > 0 && text[i - 1] === '\n' && text[i] === '\n') {
      if (!isInsideQuote(text, startPos, i)) {
        return Math.min(i + 1, targetEnd); // Split after the double newline
      }
    }
  }
  
  // Look for sentence end outside quotes (split after the punctuation)
  for (let i = targetEnd - 1; i >= minPos; i--) {
    const char = text[i];
    if ((char === '.' || char === '!' || char === '?') && 
        !isInsideQuote(text, startPos, i + 1)) {
      // Find end of whitespace after punctuation
      let splitPos = i + 1;
      while (splitPos < targetEnd && /\s/.test(text[splitPos])) {
        splitPos++;
      }
      return Math.min(splitPos, targetEnd);
    }
  }
  
  // Fallback: find any whitespace outside quotes
  for (let i = targetEnd - 1; i >= minPos; i--) {
    if (/\s/.test(text[i]) && !isInsideQuote(text, startPos, i)) {
      return i + 1;
    }
  }
  
  // Last resort: split at target end (may break quote, but LLM can handle it)
  return targetEnd;
}

// Split text into chunks at natural boundaries, avoiding quote splits
export function splitTextIntoChunks(text: string, maxChunkSize: number = 2000): string[] {
  if (text.length <= maxChunkSize) {
    return [text];
  }

  const chunks: string[] = [];
  let startPos = 0;
  
  while (startPos < text.length) {
    // If remaining text fits in one chunk, add it
    if (text.length - startPos <= maxChunkSize) {
      chunks.push(text.slice(startPos));
      break;
    }
    
    // Find safe split point (constrained to current chunk window)
    const targetEnd = Math.min(startPos + maxChunkSize, text.length);
    let splitPoint = findSafeSplitPoint(text, startPos, targetEnd);
    
    // Ensure we make progress (avoid infinite loop)
    if (splitPoint <= startPos) {
      splitPoint = targetEnd;
    }
    
    // Extract chunk (preserve all text including whitespace)
    const chunk = text.slice(startPos, splitPoint);
    if (chunk.length > 0) {
      chunks.push(chunk);
    }
    
    // Move to next position (don't skip any characters)
    startPos = splitPoint;
  }
  
  return chunks;
}

// Parse a single chunk with the LLM
async function parseChunkWithLLM(
  text: string,
  model: string,
  knownSpeakers: string[],
  potentialNames: string[]
): Promise<ParsedTextResult> {
  const speakerHint = knownSpeakers.length > 0 
    ? `\n\nKnown speakers in this text: ${knownSpeakers.join(", ")}`
    : "";
  
  const nameHint = potentialNames.length > 0 
    ? `\n\nPotential character names detected: ${potentialNames.join(", ")}`
    : "";

  const systemPrompt = `You are an expert text analyzer for audiobook production. Your task is to parse narrative text and identify:
1. Dialogue sections (text within quotes that is spoken by a character)
2. Narration sections (descriptive text not spoken by characters)
3. The speaker of each dialogue section

Rules:
- Dialogue is ONLY text within quotation marks (straight " or curly "")
- The speaker is typically mentioned before or after the dialogue (e.g., "Hello," said John)
- If no speaker is clearly identified, use null
- Preserve the exact text content including quotes
- Include ALL text - both dialogue and narration${speakerHint}${nameHint}

Return a JSON object with this structure:
{
  "segments": [
    {"text": "exact text content", "type": "dialogue" or "narration", "speaker": "Name" or null}
  ],
  "detectedSpeakers": ["list of all unique speaker names found"]
}

Important: The segments should cover the ENTIRE input text in order, with no gaps or overlaps.`;

  const userPrompt = `Parse the following text into dialogue and narration segments, identifying speakers:

${text}`;

  const response = await openrouter.chat.completions.create({
    model,
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userPrompt },
    ],
    max_tokens: 8192,
    temperature: 0.1,
    response_format: { type: "json_object" },
  });

  const content = response.choices[0]?.message?.content;
  if (!content) {
    throw new Error("No response from LLM");
  }

  const parsed = JSON.parse(content) as ParsedTextResult;
  
  if (!Array.isArray(parsed.segments)) {
    throw new Error("Invalid response format: segments not an array");
  }
  
  if (!Array.isArray(parsed.detectedSpeakers)) {
    parsed.detectedSpeakers = [];
  }

  return parsed;
}

export async function parseTextWithLLM(
  text: string,
  model: string = "meta-llama/llama-3.3-70b-instruct",
  knownSpeakers: string[] = []
): Promise<ParsedTextResult> {
  if (!isOpenRouterConfigured()) {
    throw new Error("OpenRouter is not configured");
  }

  // Extract potential names from the full text first
  const potentialNames = extractPotentialNames(text);
  
  // Combine known speakers with extracted names (known speakers take priority)
  const allKnownNames = Array.from(new Set([...knownSpeakers, ...potentialNames]));
  
  // Split text into manageable chunks
  const chunks = splitTextIntoChunks(text, 2000);
  
  // If only one chunk, parse directly
  if (chunks.length === 1) {
    return parseChunkWithLLM(text, model, knownSpeakers, potentialNames);
  }
  
  // Parse each chunk and merge results
  const allSegments: SpeakerSegment[] = [];
  const allSpeakers = new Set<string>(knownSpeakers);
  
  for (const chunk of chunks) {
    const result = await parseChunkWithLLM(chunk, model, Array.from(allSpeakers), allKnownNames);
    allSegments.push(...result.segments);
    result.detectedSpeakers.forEach(s => allSpeakers.add(s));
  }

  return {
    segments: allSegments,
    detectedSpeakers: Array.from(allSpeakers),
  };
}

export async function getAvailableModels(): Promise<string[]> {
  return [
    "openai/chatgpt-5.2",
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "deepseek/deepseek-chat",
  ];
}

export { openrouter };
