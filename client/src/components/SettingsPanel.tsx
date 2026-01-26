import { Settings, Sliders, Volume2, Cpu, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";
import type { TTSEngine } from "@shared/schema";

interface TTSEngineOption {
  id: TTSEngine;
  name: string;
  description: string;
  badge?: string;
  badgeVariant?: "default" | "secondary" | "destructive" | "outline";
}

const TTS_ENGINES: TTSEngineOption[] = [
  {
    id: "edge-tts",
    name: "Edge TTS (Azure Neural)",
    description: "47 English neural voices, free, high quality",
    badge: "Recommended",
    badgeVariant: "default",
  },
  {
    id: "openai",
    name: "OpenAI TTS",
    description: "6 premium voices, requires API key",
    badge: "API Key",
    badgeVariant: "secondary",
  },
  {
    id: "chatterbox-free",
    name: "Chatterbox Free (HuggingFace)",
    description: "Voice cloning via free HuggingFace Spaces, 300 char limit",
    badge: "Free",
    badgeVariant: "outline",
  },
  {
    id: "chatterbox-paid",
    name: "Chatterbox Paid (Custom API)",
    description: "Voice cloning via custom endpoint, no char limit",
    badge: "API Key",
    badgeVariant: "secondary",
  },
  {
    id: "piper",
    name: "Piper TTS",
    description: "Fast open source TTS, many voices",
    badge: "Local",
    badgeVariant: "outline",
  },
];

interface SettingsPanelProps {
  exaggeration: number;
  pauseDuration: number;
  ttsEngine: TTSEngine;
  onExaggerationChange: (value: number) => void;
  onPauseDurationChange: (value: number) => void;
  onTTSEngineChange: (engine: TTSEngine) => void;
}

export function SettingsPanel({
  exaggeration,
  pauseDuration,
  ttsEngine,
  onExaggerationChange,
  onPauseDurationChange,
  onTTSEngineChange,
}: SettingsPanelProps) {
  const selectedEngine = TTS_ENGINES.find(e => e.id === ttsEngine);

  const { data: chatterboxStatus } = useQuery<{
    free: { available: boolean; max_chars: number };
    paid: { configured: boolean; api_url_set: boolean; api_key_set: boolean };
  }>({
    queryKey: ["/api/chatterbox-status"],
    enabled: ttsEngine === "chatterbox-paid",
  });

  const showPaidWarning = ttsEngine === "chatterbox-paid" && chatterboxStatus && !chatterboxStatus.paid.configured;

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
            </SelectContent>
          </Select>
          {selectedEngine && (
            <p className="text-xs text-muted-foreground">
              {selectedEngine.description}
            </p>
          )}
          {showPaidWarning && (
            <Alert variant="destructive" className="mt-2">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="text-xs">
                Chatterbox Paid API not configured. Set CHATTERBOX_API_URL and CHATTERBOX_API_KEY environment variables. Will fall back to free tier.
              </AlertDescription>
            </Alert>
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
