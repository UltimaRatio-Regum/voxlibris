import { Settings, Sliders, Cpu } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { TTS_ENGINES } from "@/lib/tts-engines";
import type { TTSEngine, NarratorEmotion, DialogueEmotionMode } from "@shared/schema";

const CANONICAL_EMOTIONS: { value: NarratorEmotion; label: string }[] = [
  { value: "auto", label: "Auto-detect" },
  { value: "neutral", label: "Neutral" },
  { value: "happy", label: "Happy" },
  { value: "sad", label: "Sad" },
  { value: "angry", label: "Angry" },
  { value: "fear", label: "Fear" },
  { value: "disgust", label: "Disgust" },
  { value: "surprise", label: "Surprise" },
  { value: "excited", label: "Excited" },
  { value: "calm", label: "Calm" },
  { value: "anxious", label: "Anxious" },
  { value: "hopeful", label: "Hopeful" },
  { value: "melancholy", label: "Melancholy" },
  { value: "tender", label: "Tender" },
  { value: "proud", label: "Proud" },
];

const DIALOGUE_EMOTION_MODES: { value: DialogueEmotionMode; label: string; description: string }[] = [
  { value: "per-chunk", label: "Per chunk (default)", description: "Each chunk uses its own detected emotion" },
  { value: "first-chunk", label: "Use first chunk's emotion", description: "All chunks in a quote inherit the first chunk's emotion" },
  { value: "word-count-majority", label: "Dominant emotion (by word count)", description: "Uses the emotion associated with the most words" },
];

export interface RegisteredEngine {
  id: number;
  engine_id: string;
  engine_name: string;
  base_url: string;
  supports_voice_cloning: boolean;
  builtin_voices: Array<{ id: string; display_name: string; extra_info?: string }>;
  base_voices: Array<{ id: string; display_name: string; extra_info?: string }>;
  supported_emotions: string[];
  last_test_success: boolean | null;
}

interface SettingsPanelProps {
  exaggeration: number;
  pauseDuration: number;
  ttsEngine: TTSEngine;
  narratorEmotion?: NarratorEmotion;
  dialogueEmotionMode?: DialogueEmotionMode;
  registeredEngines?: RegisteredEngine[];
  onExaggerationChange: (value: number) => void;
  onPauseDurationChange: (value: number) => void;
  onTTSEngineChange: (engine: TTSEngine) => void;
  onNarratorEmotionChange?: (value: NarratorEmotion) => void;
  onDialogueEmotionModeChange?: (value: DialogueEmotionMode) => void;
}

export function SettingsPanel({
  exaggeration,
  pauseDuration,
  ttsEngine,
  narratorEmotion = "auto",
  dialogueEmotionMode = "per-chunk",
  registeredEngines = [],
  onExaggerationChange,
  onPauseDurationChange,
  onTTSEngineChange,
  onNarratorEmotionChange,
  onDialogueEmotionModeChange,
}: SettingsPanelProps) {
  const selectedBuiltIn = TTS_ENGINES.find(e => e.id === ttsEngine);
  const selectedRegistered = registeredEngines.find(e => e.engine_id === ttsEngine);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Settings className="h-5 w-5 text-primary" />
          Generation Settings
        </CardTitle>
        <CardDescription className="mt-1">
          Fine-tune the audio output
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-muted-foreground" />
              TTS Engine
            </Label>
            <p className="text-xs text-muted-foreground">
              Choose the text-to-speech engine
            </p>
          </div>
          <Select value={ttsEngine} onValueChange={(v) => onTTSEngineChange(v as TTSEngine)}>
            <SelectTrigger data-testid="select-tts-engine">
              <SelectValue placeholder="Select TTS engine" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectLabel>Built-in Engines</SelectLabel>
                {TTS_ENGINES.map((engine) => (
                  <SelectItem key={engine.id} value={engine.id} data-testid={`option-engine-${engine.id}`}>
                    <div className="flex items-center gap-2">
                      <span>{engine.name}</span>
                      {engine.badge && (
                        <Badge variant={engine.badgeVariant} className="text-xs py-0 px-1.5">
                          {engine.badge}
                        </Badge>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectGroup>
              {registeredEngines.length > 0 && (
                <SelectGroup>
                  <SelectLabel>Remote Engines</SelectLabel>
                  {registeredEngines.map((engine) => (
                    <SelectItem key={engine.engine_id} value={engine.engine_id} data-testid={`option-engine-${engine.engine_id}`}>
                      <div className="flex items-center gap-2">
                        <span>{engine.engine_name}</span>
                        {engine.supports_voice_cloning && (
                          <Badge variant="secondary" className="text-xs py-0 px-1.5">
                            Cloning
                          </Badge>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectGroup>
              )}
            </SelectContent>
          </Select>
          {selectedBuiltIn && (
            <p className="text-xs text-muted-foreground">
              {selectedBuiltIn.description}
            </p>
          )}
          {selectedRegistered && (
            <p className="text-xs text-muted-foreground">
              Remote engine: {selectedRegistered.base_url}
              {selectedRegistered.supports_voice_cloning ? " • Supports voice cloning" : ""}
            </p>
          )}
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="flex items-center gap-2">
                <Sliders className="h-4 w-4 text-muted-foreground" />
                Emotion Intensity
              </Label>
              <p className="text-xs text-muted-foreground">
                Controls how expressive the voice is
              </p>
            </div>
            <span className="text-sm font-mono bg-muted px-2 py-1 rounded">
              {exaggeration.toFixed(2)}
            </span>
          </div>
          <Slider
            value={[exaggeration]}
            min={0}
            max={1}
            step={0.05}
            onValueChange={([v]) => onExaggerationChange(v)}
            data-testid="slider-exaggeration"
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Monotone</span>
            <span>Dramatic</span>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="flex items-center gap-2">
                <Settings className="h-4 w-4 text-muted-foreground" />
                Pause Between Segments
              </Label>
              <p className="text-xs text-muted-foreground">
                Silence duration between text segments
              </p>
            </div>
            <span className="text-sm font-mono bg-muted px-2 py-1 rounded">
              {pauseDuration}ms
            </span>
          </div>
          <Slider
            value={[pauseDuration]}
            min={0}
            max={3000}
            step={100}
            onValueChange={([v]) => onPauseDurationChange(v)}
            data-testid="slider-pause-duration"
          />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>No pause</span>
            <span>3 seconds</span>
          </div>
        </div>

        {onNarratorEmotionChange && (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="flex items-center gap-2">
                <Sliders className="h-4 w-4 text-muted-foreground" />
                Narrator Emotion
              </Label>
              <p className="text-xs text-muted-foreground">
                Override detected emotions for narration segments
              </p>
            </div>
            <Select value={narratorEmotion} onValueChange={(v) => onNarratorEmotionChange(v as NarratorEmotion)}>
              <SelectTrigger data-testid="select-narrator-emotion">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CANONICAL_EMOTIONS.map((e) => (
                  <SelectItem key={e.value} value={e.value} data-testid={`option-narrator-emotion-${e.value}`}>
                    {e.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {onDialogueEmotionModeChange && (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label className="flex items-center gap-2">
                <Sliders className="h-4 w-4 text-muted-foreground" />
                Dialogue Emotion Mode
              </Label>
              <p className="text-xs text-muted-foreground">
                How to handle emotions when a quote spans multiple chunks
              </p>
            </div>
            <Select value={dialogueEmotionMode} onValueChange={(v) => onDialogueEmotionModeChange(v as DialogueEmotionMode)}>
              <SelectTrigger data-testid="select-dialogue-emotion-mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DIALOGUE_EMOTION_MODES.map((m) => (
                  <SelectItem key={m.value} value={m.value} data-testid={`option-dialogue-mode-${m.value}`}>
                    <div>
                      <span>{m.label}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
