import { z } from "zod";

// TTS Engine types
export const ttsEngineSchema = z.enum([
  "edge-tts",          // Microsoft Azure Neural TTS - free, 300+ voices
  "openai",            // OpenAI TTS - requires API key
  "chatterbox-free",   // Chatterbox TTS - free HuggingFace Spaces API
  "chatterbox-paid",   // Chatterbox TTS - paid custom API endpoint
  "piper",             // Piper TTS - open source, fast, local
  "soprano",           // Soprano TTS - ultra-fast local 80M model
]);

export type TTSEngine = z.infer<typeof ttsEngineSchema>;

// TTS Engine metadata
export const ttsEngineInfoSchema = z.object({
  id: ttsEngineSchema,
  name: z.string(),
  description: z.string(),
  supportsVoiceCloning: z.boolean(),
  requiresApiKey: z.boolean(),
  voiceType: z.enum(["preset", "cloning", "both"]),
});

export type TTSEngineInfo = z.infer<typeof ttsEngineInfoSchema>;

// Edge-TTS voice (preset neural voice)
export const edgeVoiceSchema = z.object({
  id: z.string(),           // e.g., "en-US-AriaNeural"
  name: z.string(),         // e.g., "Microsoft Aria Online (Natural)"
  gender: z.string(),       // "Male" or "Female"
  locale: z.string(),       // e.g., "en-US"
});

export type EdgeVoice = z.infer<typeof edgeVoiceSchema>;

// OpenAI TTS voice
export const openaiVoiceSchema = z.object({
  id: z.string(),           // e.g., "alloy"
  name: z.string(),         // e.g., "Alloy"
  description: z.string(),  // e.g., "Neutral, balanced voice"
});

export type OpenAIVoice = z.infer<typeof openaiVoiceSchema>;

// Voice sample for TTS
export const voiceSampleSchema = z.object({
  id: z.string(),
  name: z.string(),
  audioUrl: z.string(),
  duration: z.number(),
  createdAt: z.string(),
});

export type VoiceSample = z.infer<typeof voiceSampleSchema>;

export const insertVoiceSampleSchema = voiceSampleSchema.omit({ id: true, createdAt: true });
export type InsertVoiceSample = z.infer<typeof insertVoiceSampleSchema>;

// Voice library entry (pre-uploaded voice samples)
export const libraryVoiceSchema = z.object({
  id: z.string(),           // e.g., "p226"
  name: z.string(),         // e.g., "Voice 226: M/22 Surrey, England"
  gender: z.enum(["M", "F"]),
  age: z.number(),
  language: z.string(),     // e.g., "English", "Scottish"
  location: z.string(),     // e.g., "Surrey", "Southern_England"
  audioUrl: z.string(),     // URL to mic1 file
  altAudioUrl: z.string().nullable(), // URL to mic2 file if available
  transcript: z.string().nullable(),  // Text content of transcript
  duration: z.number(),
});

export type LibraryVoice = z.infer<typeof libraryVoiceSchema>;

// Text segment types
export const segmentTypeEnum = z.enum(["narration", "dialogue"]);
export type SegmentType = z.infer<typeof segmentTypeEnum>;

// Sentiment for prosody control
export const sentimentSchema = z.object({
  label: z.enum(["positive", "negative", "neutral", "excited", "sad", "angry", "fearful"]),
  score: z.number().min(0).max(1),
});

export type Sentiment = z.infer<typeof sentimentSchema>;

// Speaker confidence scores for dialogue segments
export const speakerCandidatesSchema = z.record(z.string(), z.number().min(0).max(1));
export type SpeakerCandidates = z.infer<typeof speakerCandidatesSchema>;

// Text segment after parsing
export const textSegmentSchema = z.object({
  id: z.string(),
  type: segmentTypeEnum,
  text: z.string(),
  speaker: z.string().nullable(),
  speakerCandidates: speakerCandidatesSchema.nullable(), // Confidence scores for each potential speaker
  needsReview: z.boolean().default(false), // True if low variance between speaker candidates
  sentiment: sentimentSchema.nullable(),
  startIndex: z.number(),
  endIndex: z.number(),
  chunkId: z.number().optional(), // For grouping into ~30s chunks
  approxDurationSeconds: z.number().optional(), // Estimated audio duration
});

export type TextSegment = z.infer<typeof textSegmentSchema>;

// Audio chunk after TTS processing
export const audioChunkSchema = z.object({
  id: z.string(),
  segmentId: z.string(),
  audioUrl: z.string(),
  duration: z.number(),
  pitchShift: z.number(),
  speedFactor: z.number(),
});

export type AudioChunk = z.infer<typeof audioChunkSchema>;

// Speaker configuration
export const speakerConfigSchema = z.object({
  name: z.string(),
  voiceSampleId: z.string().nullable(),
  pitchOffset: z.number().default(0),
  speedFactor: z.number().default(1.0),
});

export type SpeakerConfig = z.infer<typeof speakerConfigSchema>;

// Project configuration
export const projectConfigSchema = z.object({
  narratorVoiceId: z.string().nullable(),
  defaultExaggeration: z.number().min(0).max(1).default(0.5),
  pauseBetweenSegments: z.number().min(0).max(3000).default(500),
  speakers: z.record(z.string(), speakerConfigSchema),
  ttsEngine: ttsEngineSchema.default("edge-tts"),
});

export type ProjectConfig = z.infer<typeof projectConfigSchema>;

// Audiobook project
export const audiobookProjectSchema = z.object({
  id: z.string(),
  title: z.string(),
  text: z.string(),
  segments: z.array(textSegmentSchema),
  config: projectConfigSchema,
  status: z.enum(["draft", "processing", "completed", "error"]),
  progress: z.number().min(0).max(100).default(0),
  outputUrl: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type AudiobookProject = z.infer<typeof audiobookProjectSchema>;

export const insertProjectSchema = z.object({
  title: z.string().min(1),
  text: z.string().min(1),
});

export type InsertProject = z.infer<typeof insertProjectSchema>;

// API request/response types
export const parseTextRequestSchema = z.object({
  text: z.string().min(1),
});

export type ParseTextRequest = z.infer<typeof parseTextRequestSchema>;

export const parseTextResponseSchema = z.object({
  segments: z.array(textSegmentSchema),
  detectedSpeakers: z.array(z.string()),
});

export type ParseTextResponse = z.infer<typeof parseTextResponseSchema>;

export const generateAudioRequestSchema = z.object({
  projectId: z.string(),
});

export type GenerateAudioRequest = z.infer<typeof generateAudioRequestSchema>;

export const progressUpdateSchema = z.object({
  projectId: z.string(),
  progress: z.number(),
  currentSegment: z.number(),
  totalSegments: z.number(),
  status: z.string(),
});

export type ProgressUpdate = z.infer<typeof progressUpdateSchema>;

// Legacy user types (kept for compatibility)
export const userSchema = z.object({
  id: z.string(),
  username: z.string(),
  password: z.string(),
});

export type User = z.infer<typeof userSchema>;

export const insertUserSchema = userSchema.omit({ id: true });
export type InsertUser = z.infer<typeof insertUserSchema>;
