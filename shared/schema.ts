import { z } from "zod";

// TTS Engine types
export const ttsEngineSchema = z.string();

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
export const CANONICAL_EMOTIONS = [
  "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
  "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
] as const;

export const sentimentSchema = z.object({
  label: z.string(),
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
  wordCount: z.number().optional(),
  chunkId: z.number().optional(),
  approxDurationSeconds: z.number().optional(),
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

export const narratorEmotionSchema = z.enum([
  "auto", "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
  "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
]);
export type NarratorEmotion = z.infer<typeof narratorEmotionSchema>;

export const dialogueEmotionModeSchema = z.enum([
  "per-chunk", "first-chunk", "word-count-majority",
]);
export type DialogueEmotionMode = z.infer<typeof dialogueEmotionModeSchema>;

// Project configuration
export const projectConfigSchema = z.object({
  narratorVoiceId: z.string().nullable(),
  baseVoiceId: z.string().nullable().optional(),
  defaultExaggeration: z.number().min(0).max(1).default(0.5),
  pauseBetweenSegments: z.number().min(0).max(3000).default(500),
  speakers: z.record(z.string(), speakerConfigSchema),
  ttsEngine: ttsEngineSchema.default("edge-tts"),
  narratorEmotion: narratorEmotionSchema.default("auto"),
  dialogueEmotionMode: dialogueEmotionModeSchema.default("per-chunk"),
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

// TTS Job types
export const jobStatusSchema = z.enum(["pending", "waiting", "processing", "completed", "failed", "cancelled"]);
export type JobStatus = z.infer<typeof jobStatusSchema>;

export const segmentStatusSchema = z.enum(["pending", "processing", "completed", "failed"]);
export type SegmentStatus = z.infer<typeof segmentStatusSchema>;

export const ttsJobSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: jobStatusSchema,
  totalSegments: z.number(),
  completedSegments: z.number(),
  failedSegments: z.number().default(0),
  ttsEngine: z.string(),
  narratorVoiceId: z.string().nullable(),
  errorMessage: z.string().nullable(),
  jobGroupId: z.string().nullable().optional(),
  createdAt: z.string().nullable(),
  updatedAt: z.string().nullable(),
  progress: z.number(),
});

export type TTSJob = z.infer<typeof ttsJobSchema>;

export const ttsSegmentSchema = z.object({
  id: z.string(),
  segmentIndex: z.number(),
  text: z.string(),
  type: z.string(),
  speaker: z.string().nullable(),
  sentiment: z.string().nullable(),
  status: segmentStatusSchema,
  audioPath: z.string().nullable(),
  hasAudio: z.boolean(),
  durationSeconds: z.number().nullable(),
  errorMessage: z.string().nullable(),
});

export type TTSSegmentStatus = z.infer<typeof ttsSegmentSchema>;

// Project system types
export const projectStatusSchema = z.enum(["draft", "segmenting", "segmented", "generating", "completed", "failed"]);
export type ProjectStatus = z.infer<typeof projectStatusSchema>;

export const projectChunkSchema = z.object({
  id: z.string(),
  sectionId: z.string(),
  chunkIndex: z.number(),
  text: z.string(),
  segmentType: z.enum(["narration", "dialogue"]),
  speaker: z.string().nullable(),
  emotion: z.string(),
  speakerOverride: z.string().nullable(),
  emotionOverride: z.string().nullable(),
  wordCount: z.number(),
  approxDurationSeconds: z.number(),
});
export type ProjectChunk = z.infer<typeof projectChunkSchema>;

export const projectSectionSchema = z.object({
  id: z.string(),
  chapterId: z.string(),
  sectionIndex: z.number(),
  title: z.string().nullable().optional(),
  status: z.string(),
  errorMessage: z.string().nullable(),
  chunks: z.array(projectChunkSchema).optional(),
});
export type ProjectSection = z.infer<typeof projectSectionSchema>;

export const projectChapterSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  chapterIndex: z.number(),
  title: z.string().nullable(),
  status: z.string(),
  speakersJson: z.string().nullable(),
  ttsEngine: z.string().nullable(),
  narratorVoiceId: z.string().nullable(),
  errorMessage: z.string().nullable(),
  wordCount: z.number().optional(),
  sections: z.array(projectSectionSchema).optional(),
});
export type ProjectChapter = z.infer<typeof projectChapterSchema>;

export const projectAudioFileSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  scopeType: z.string(),
  scopeId: z.string(),
  format: z.string(),
  durationSeconds: z.number().nullable(),
  ttsEngine: z.string().nullable(),
  voiceId: z.string().nullable(),
  settingsJson: z.string().nullable(),
  label: z.string().nullable().optional(),
  createdAt: z.string().nullable(),
});
export type ProjectAudioFile = z.infer<typeof projectAudioFileSchema>;

export const outputFormatSchema = z.enum(["mp3", "mp3-chapters", "m4b"]);
export type OutputFormat = z.infer<typeof outputFormatSchema>;

export const projectSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: projectStatusSchema,
  ttsEngine: z.string(),
  narratorVoiceId: z.string().nullable(),
  baseVoiceId: z.string().nullable().optional(),
  exaggeration: z.number(),
  pauseDuration: z.number(),
  speakersJson: z.string().nullable(),
  sourceType: z.string(),
  sourceFilename: z.string().nullable(),
  errorMessage: z.string().nullable(),
  narratorEmotion: narratorEmotionSchema.default("auto"),
  dialogueEmotionMode: dialogueEmotionModeSchema.default("per-chunk"),
  outputFormat: outputFormatSchema.default("mp3"),
  metaAuthor: z.string().nullable(),
  metaNarrator: z.string().nullable(),
  metaGenre: z.string().nullable(),
  metaYear: z.string().nullable(),
  metaDescription: z.string().nullable(),
  hasCoverImage: z.boolean().default(false),
  createdAt: z.string().nullable(),
  updatedAt: z.string().nullable(),
  chapters: z.array(projectChapterSchema).optional(),
  audioFiles: z.array(projectAudioFileSchema).optional(),
});
export type ProjectData = z.infer<typeof projectSchema>;

export const projectListItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: projectStatusSchema,
  sourceType: z.string(),
  chapterCount: z.number(),
  totalChunks: z.number(),
  createdAt: z.string().nullable(),
  updatedAt: z.string().nullable(),
});
export type ProjectListItem = z.infer<typeof projectListItemSchema>;

export const createProjectRequestSchema = z.object({
  title: z.string().min(1),
  text: z.string().optional(),
});
export type CreateProjectRequest = z.infer<typeof createProjectRequestSchema>;

export const updateProjectSettingsSchema = z.object({
  ttsEngine: z.string().optional(),
  narratorVoiceId: z.string().nullable().optional(),
  baseVoiceId: z.string().nullable().optional(),
  exaggeration: z.number().min(0).max(1).optional(),
  pauseDuration: z.number().min(0).max(3000).optional(),
  speakersJson: z.string().nullable().optional(),
  outputFormat: outputFormatSchema.optional(),
  metaAuthor: z.string().nullable().optional(),
  metaNarrator: z.string().nullable().optional(),
  metaGenre: z.string().nullable().optional(),
  metaYear: z.string().nullable().optional(),
  metaDescription: z.string().nullable().optional(),
});
export type UpdateProjectSettings = z.infer<typeof updateProjectSettingsSchema>;

export const generateProjectAudioRequestSchema = z.object({
  scopeType: z.enum(["chunk", "section", "chapter", "project"]),
  scopeId: z.string(),
});
export type GenerateProjectAudioRequest = z.infer<typeof generateProjectAudioRequestSchema>;

// Legacy user types (kept for compatibility)
export const userSchema = z.object({
  id: z.string(),
  username: z.string(),
  password: z.string(),
});

export type User = z.infer<typeof userSchema>;

export const insertUserSchema = userSchema.omit({ id: true });
export type InsertUser = z.infer<typeof insertUserSchema>;
