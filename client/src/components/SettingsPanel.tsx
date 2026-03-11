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
import type { TTSEngine } from "@shared/schema";

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
  registeredEngines?: RegisteredEngine[];
  onExaggerationChange: (value: number) => void;
  onPauseDurationChange: (value: number) => void;
  onTTSEngineChange: (engine: TTSEngine) => void;
}

export function SettingsPanel({
  exaggeration,
  pauseDuration,
  ttsEngine,
  registeredEngines = [],
  onExaggerationChange,
  onPauseDurationChange,
  onTTSEngineChange,
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
      </CardContent>
    </Card>
  );
}
