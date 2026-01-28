import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, RotateCcw, Volume2, Gauge, Music, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";

interface ProsodySettings {
  pitch: Record<string, number>;
  speed: Record<string, number>;
  volume: Record<string, number>;
  intensity: Record<string, number>;
  emotions: string[];
}

interface EdgeVoice {
  id: string;
  name: string;
  gender: string;
  locale: string;
}

interface OpenAIVoice {
  id: string;
  name: string;
  description: string;
}

interface LibraryVoice {
  id: string;
  name: string;
  gender: string;
}

const TTS_ENGINES = [
  { value: "edge-tts", label: "Edge TTS (Recommended)" },
  { value: "openai", label: "OpenAI TTS" },
  { value: "chatterbox-free", label: "Chatterbox Free" },
  { value: "hf-tts-paid", label: "HuggingFace TTS Paid" },
  { value: "piper", label: "Piper TTS" },
  { value: "soprano", label: "Soprano TTS" },
];

const CHATTERBOX_MODELS = [
  { value: "qwen3", label: "Qwen3 TTS (Best quality)" },
  { value: "chatterbox", label: "Chatterbox (Fast)" },
  { value: "xtts_v2", label: "XTTS v2 (Multilingual)" },
  { value: "styletts2", label: "StyleTTS2 (Expressive)" },
];

const DEFAULT_PROSODY: ProsodySettings = {
  pitch: {
    neutral: 0, happy: 0.12, sad: -0.12, angry: 0.12,
    fearful: 0.12, surprised: 0.12, disgusted: -0.12, excited: 0.12,
    calm: 0, anxious: 0.06, hopeful: 0.06, melancholy: -0.06,
  },
  speed: {
    neutral: 1.0, happy: 1.01, sad: 0.99, angry: 1.01,
    fearful: 1.01, surprised: 1.01, disgusted: 0.99, excited: 1.01,
    calm: 0.99, anxious: 1.01, hopeful: 1.0, melancholy: 0.99,
  },
  volume: {
    neutral: 1.0, happy: 1.05, sad: 0.95, angry: 1.1,
    fearful: 0.95, surprised: 1.08, disgusted: 1.02, excited: 1.1,
    calm: 0.95, anxious: 1.03, hopeful: 1.02, melancholy: 0.93,
  },
  intensity: {
    neutral: 0.3, happy: 0.6, sad: 0.5, angry: 0.7,
    fearful: 0.6, surprised: 0.7, disgusted: 0.5, excited: 0.8,
    calm: 0.2, anxious: 0.6, hopeful: 0.5, melancholy: 0.4,
  },
  emotions: [
    "neutral", "happy", "sad", "angry", "fearful", "surprised",
    "disgusted", "excited", "calm", "anxious", "hopeful", "melancholy"
  ],
};

export function SettingsTab() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [defaultEngine, setDefaultEngine] = useState(() => 
    localStorage.getItem("voxlibris-default-engine") || "edge-tts"
  );
  const [defaultVoice, setDefaultVoice] = useState(() =>
    localStorage.getItem("voxlibris-default-voice") || ""
  );
  const [pauseBetweenSegments, setPauseBetweenSegments] = useState(() =>
    parseInt(localStorage.getItem("voxlibris-pause-between-segments") || "500", 10)
  );
  const [maxSilenceMs, setMaxSilenceMs] = useState(() =>
    parseInt(localStorage.getItem("voxlibris-max-silence-ms") || "300", 10)
  );
  const [chatterboxModel, setChatterboxModel] = useState(() =>
    localStorage.getItem("voxlibris-chatterbox-model") || "qwen3"
  );
  const [stAlpha, setStAlpha] = useState(() =>
    parseFloat(localStorage.getItem("voxlibris-styletts-alpha") || "0.3")
  );
  const [stBeta, setStBeta] = useState(() =>
    parseFloat(localStorage.getItem("voxlibris-styletts-beta") || "0.7")
  );
  const [stDiffusionSteps, setStDiffusionSteps] = useState(() =>
    parseInt(localStorage.getItem("voxlibris-styletts-diffusion-steps") || "5", 10)
  );
  const [stEmbeddingScale, setStEmbeddingScale] = useState(() =>
    parseFloat(localStorage.getItem("voxlibris-styletts-embedding-scale") || "1.0")
  );
  const [localProsody, setLocalProsody] = useState<ProsodySettings | null>(null);

  interface TTSSettings {
    chatterbox_model: string;
    st_alpha: number;
    st_beta: number;
    st_diffusion_steps: number;
    st_embedding_scale: number;
  }

  const { data: ttsSettingsData } = useQuery<TTSSettings>({
    queryKey: ["/api/tts-settings"],
  });

  useEffect(() => {
    if (ttsSettingsData) {
      setChatterboxModel(ttsSettingsData.chatterbox_model);
      setStAlpha(ttsSettingsData.st_alpha);
      setStBeta(ttsSettingsData.st_beta);
      setStDiffusionSteps(ttsSettingsData.st_diffusion_steps);
      setStEmbeddingScale(ttsSettingsData.st_embedding_scale);
    }
  }, [ttsSettingsData]);

  const saveTTSSettingsMutation = useMutation({
    mutationFn: async (settings: TTSSettings) => {
      const response = await apiRequest("POST", "/api/tts-settings", settings);
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/tts-settings"] });
    },
  });

  const { data: prosodyData } = useQuery<ProsodySettings>({
    queryKey: ["/api/prosody-settings"],
  });

  const { data: edgeVoicesData } = useQuery<{ voices: EdgeVoice[] }>({
    queryKey: ["/api/edge-voices"],
    enabled: defaultEngine === "edge-tts",
  });

  const { data: openaiVoicesData } = useQuery<{ voices: OpenAIVoice[] }>({
    queryKey: ["/api/openai-voices"],
    enabled: defaultEngine === "openai",
  });

  const isVoiceCloningEngine = ["chatterbox-free", "hf-tts-paid"].includes(defaultEngine);
  
  const { data: libraryVoicesData } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library"],
    enabled: isVoiceCloningEngine,
  });

  useEffect(() => {
    if (prosodyData && !localProsody) {
      setLocalProsody(prosodyData);
    }
  }, [prosodyData, localProsody]);

  const saveProsodyMutation = useMutation({
    mutationFn: async (settings: ProsodySettings) => {
      const response = await apiRequest("POST", "/api/prosody-settings", {
        pitch: settings.pitch,
        speed: settings.speed,
        volume: settings.volume,
        intensity: settings.intensity,
      });
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/prosody-settings"] });
      toast({ title: "Settings saved", description: "Prosody settings updated successfully" });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to save", description: error.message, variant: "destructive" });
    },
  });

  const handleEngineChange = (engine: string) => {
    setDefaultEngine(engine);
    setDefaultVoice("");
    localStorage.setItem("voxlibris-default-engine", engine);
    localStorage.removeItem("voxlibris-default-voice");
  };

  const handleVoiceChange = (voice: string) => {
    setDefaultVoice(voice);
    localStorage.setItem("voxlibris-default-voice", voice);
  };

  const handlePauseBetweenSegmentsChange = (value: string) => {
    const num = parseInt(value, 10);
    if (!isNaN(num) && num >= 0 && num <= 5000) {
      setPauseBetweenSegments(num);
      localStorage.setItem("voxlibris-pause-between-segments", String(num));
    }
  };

  const handleMaxSilenceChange = (value: string) => {
    const num = parseInt(value, 10);
    if (!isNaN(num) && num >= 0 && num <= 5000) {
      setMaxSilenceMs(num);
      localStorage.setItem("voxlibris-max-silence-ms", String(num));
    }
  };

  const saveTTSSettings = (updates: Partial<TTSSettings>) => {
    const settings: TTSSettings = {
      chatterbox_model: updates.chatterbox_model ?? chatterboxModel,
      st_alpha: updates.st_alpha ?? stAlpha,
      st_beta: updates.st_beta ?? stBeta,
      st_diffusion_steps: updates.st_diffusion_steps ?? stDiffusionSteps,
      st_embedding_scale: updates.st_embedding_scale ?? stEmbeddingScale,
    };
    saveTTSSettingsMutation.mutate(settings);
  };

  const handleChatterboxModelChange = (value: string) => {
    setChatterboxModel(value);
    localStorage.setItem("voxlibris-chatterbox-model", value);
    saveTTSSettings({ chatterbox_model: value });
  };

  const handleStAlphaChange = (value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num) && num >= 0 && num <= 1) {
      setStAlpha(num);
      localStorage.setItem("voxlibris-styletts-alpha", String(num));
      saveTTSSettings({ st_alpha: num });
    }
  };

  const handleStBetaChange = (value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num) && num >= 0 && num <= 1) {
      setStBeta(num);
      localStorage.setItem("voxlibris-styletts-beta", String(num));
      saveTTSSettings({ st_beta: num });
    }
  };

  const handleStDiffusionStepsChange = (value: string) => {
    const num = parseInt(value, 10);
    if (!isNaN(num) && num >= 1 && num <= 20) {
      setStDiffusionSteps(num);
      localStorage.setItem("voxlibris-styletts-diffusion-steps", String(num));
      saveTTSSettings({ st_diffusion_steps: num });
    }
  };

  const handleStEmbeddingScaleChange = (value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num) && num >= 0.5 && num <= 2) {
      setStEmbeddingScale(num);
      localStorage.setItem("voxlibris-styletts-embedding-scale", String(num));
      saveTTSSettings({ st_embedding_scale: num });
    }
  };

  const handleProsodyChange = (emotion: string, field: "pitch" | "speed" | "volume" | "intensity", value: string) => {
    if (!localProsody) return;
    const numValue = parseFloat(value);
    if (isNaN(numValue)) return;
    
    setLocalProsody({
      ...localProsody,
      [field]: {
        ...localProsody[field],
        [emotion]: numValue,
      },
    });
  };

  const handleSaveProsody = () => {
    if (localProsody) {
      saveProsodyMutation.mutate(localProsody);
    }
  };

  const handleResetProsody = () => {
    setLocalProsody(DEFAULT_PROSODY);
    toast({ title: "Reset to defaults", description: "Click Save to apply the reset" });
  };

  const getVoiceOptions = () => {
    if (defaultEngine === "edge-tts" && edgeVoicesData?.voices) {
      return edgeVoicesData.voices.map((v) => ({
        value: `edge:${v.id}`,
        label: `${v.name} (${v.gender})`,
      }));
    }
    if (defaultEngine === "openai" && openaiVoicesData?.voices) {
      return openaiVoicesData.voices.map((v) => ({
        value: `openai:${v.id}`,
        label: `${v.name} - ${v.description}`,
      }));
    }
    if (isVoiceCloningEngine && libraryVoicesData) {
      return libraryVoicesData.map((v) => ({
        value: `library:${v.id}`,
        label: v.name,
      }));
    }
    return [];
  };

  const voiceOptions = getVoiceOptions();
  const emotions = localProsody?.emotions || DEFAULT_PROSODY.emotions;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Default TTS Settings</CardTitle>
          <CardDescription>
            Configure the default text-to-speech engine and voice for new projects
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="default-engine">Default TTS Engine</Label>
              <Select value={defaultEngine} onValueChange={handleEngineChange}>
                <SelectTrigger id="default-engine" data-testid="select-default-engine">
                  <SelectValue placeholder="Select engine" />
                </SelectTrigger>
                <SelectContent>
                  {TTS_ENGINES.map((engine) => (
                    <SelectItem key={engine.value} value={engine.value}>
                      {engine.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="default-voice">Default Voice</Label>
              <Select 
                key={`voice-select-${defaultEngine}`}
                value={defaultVoice} 
                onValueChange={handleVoiceChange}
                disabled={voiceOptions.length === 0}
              >
                <SelectTrigger id="default-voice" data-testid="select-default-voice">
                  <SelectValue placeholder={voiceOptions.length === 0 ? "Loading voices..." : "Select voice"} />
                </SelectTrigger>
                <SelectContent>
                  {voiceOptions.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 pt-4 border-t">
            <div className="space-y-2">
              <Label htmlFor="pause-between-segments">Pause Between Segments (ms)</Label>
              <Input
                id="pause-between-segments"
                type="number"
                min={0}
                max={5000}
                step={50}
                value={pauseBetweenSegments}
                onChange={(e) => handlePauseBetweenSegmentsChange(e.target.value)}
                data-testid="input-pause-between-segments"
              />
              <p className="text-xs text-muted-foreground">
                Initial silence added between audio segments (0-5000ms)
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="max-silence">Max Silence Duration (ms)</Label>
              <Input
                id="max-silence"
                type="number"
                min={0}
                max={5000}
                step={50}
                value={maxSilenceMs}
                onChange={(e) => handleMaxSilenceChange(e.target.value)}
                data-testid="input-max-silence"
              />
              <p className="text-xs text-muted-foreground">
                Compress any silence longer than this in final audio (0-5000ms)
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>HuggingFace TTS Paid Settings</CardTitle>
          <CardDescription>
            Configure the TTS model and parameters for HuggingFace TTS Paid
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="chatterbox-model">TTS Model</Label>
              <Select value={chatterboxModel} onValueChange={handleChatterboxModelChange}>
                <SelectTrigger id="chatterbox-model" data-testid="select-chatterbox-model">
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {CHATTERBOX_MODELS.map((model) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Qwen3 has best quality, StyleTTS2 is most expressive
              </p>
            </div>
          </div>

          {chatterboxModel === "styletts2" && (
            <div className="grid gap-4 md:grid-cols-2 pt-4 border-t">
              <div className="space-y-2">
                <Label htmlFor="st-alpha">Style Alpha (0-1)</Label>
                <Input
                  id="st-alpha"
                  type="number"
                  min={0}
                  max={1}
                  step={0.1}
                  value={stAlpha}
                  onChange={(e) => handleStAlphaChange(e.target.value)}
                  data-testid="input-st-alpha"
                />
                <p className="text-xs text-muted-foreground">
                  Voice style strength (higher = more stylized)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="st-beta">Style Beta (0-1)</Label>
                <Input
                  id="st-beta"
                  type="number"
                  min={0}
                  max={1}
                  step={0.1}
                  value={stBeta}
                  onChange={(e) => handleStBetaChange(e.target.value)}
                  data-testid="input-st-beta"
                />
                <p className="text-xs text-muted-foreground">
                  Prosody emphasis (higher = stronger emotion)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="st-diffusion-steps">Diffusion Steps (1-20)</Label>
                <Input
                  id="st-diffusion-steps"
                  type="number"
                  min={1}
                  max={20}
                  step={1}
                  value={stDiffusionSteps}
                  onChange={(e) => handleStDiffusionStepsChange(e.target.value)}
                  data-testid="input-st-diffusion-steps"
                />
                <p className="text-xs text-muted-foreground">
                  Quality vs speed (higher = better quality, slower)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="st-embedding-scale">Embedding Scale (0.5-2)</Label>
                <Input
                  id="st-embedding-scale"
                  type="number"
                  min={0.5}
                  max={2}
                  step={0.1}
                  value={stEmbeddingScale}
                  onChange={(e) => handleStEmbeddingScaleChange(e.target.value)}
                  data-testid="input-st-embedding-scale"
                />
                <p className="text-xs text-muted-foreground">
                  Speaker identity strength (higher = closer to reference)
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <CardTitle>Emotion Prosody Settings</CardTitle>
              <CardDescription>
                Customize how emotions affect pitch, speed, volume, and intensity (Chatterbox)
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleResetProsody}
                data-testid="button-reset-prosody"
              >
                <RotateCcw className="h-4 w-4 mr-1" />
                Reset
              </Button>
              <Button
                size="sm"
                onClick={handleSaveProsody}
                disabled={saveProsodyMutation.isPending}
                data-testid="button-save-prosody"
              >
                <Save className="h-4 w-4 mr-1" />
                Save
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[120px]">Emotion</TableHead>
                  <TableHead className="text-center">
                    <div className="flex items-center justify-center gap-1">
                      <Music className="h-4 w-4" />
                      <span>Pitch</span>
                    </div>
                  </TableHead>
                  <TableHead className="text-center">
                    <div className="flex items-center justify-center gap-1">
                      <Gauge className="h-4 w-4" />
                      <span>Speed</span>
                    </div>
                  </TableHead>
                  <TableHead className="text-center">
                    <div className="flex items-center justify-center gap-1">
                      <Volume2 className="h-4 w-4" />
                      <span>Volume</span>
                    </div>
                  </TableHead>
                  <TableHead className="text-center">
                    <div className="flex items-center justify-center gap-1">
                      <Zap className="h-4 w-4" />
                      <span>Intensity</span>
                    </div>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {emotions.map((emotion) => (
                  <TableRow key={emotion}>
                    <TableCell className="font-medium capitalize">{emotion}</TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        step="0.01"
                        value={localProsody?.pitch[emotion] ?? 0}
                        onChange={(e) => handleProsodyChange(emotion, "pitch", e.target.value)}
                        className="w-20 mx-auto text-center"
                        data-testid={`input-pitch-${emotion}`}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        step="0.01"
                        value={localProsody?.speed[emotion] ?? 1}
                        onChange={(e) => handleProsodyChange(emotion, "speed", e.target.value)}
                        className="w-20 mx-auto text-center"
                        data-testid={`input-speed-${emotion}`}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        step="0.01"
                        value={localProsody?.volume[emotion] ?? 1}
                        onChange={(e) => handleProsodyChange(emotion, "volume", e.target.value)}
                        className="w-20 mx-auto text-center"
                        data-testid={`input-volume-${emotion}`}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={localProsody?.intensity[emotion] ?? 0.5}
                        onChange={(e) => handleProsodyChange(emotion, "intensity", e.target.value)}
                        className="w-20 mx-auto text-center"
                        data-testid={`input-intensity-${emotion}`}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-4 text-sm text-muted-foreground space-y-1">
            <p><strong>Pitch:</strong> Semitones offset (-12 to +12). Positive = higher, negative = lower.</p>
            <p><strong>Speed:</strong> Factor multiplier (0.5 to 2.0). 1.0 = normal speed.</p>
            <p><strong>Volume:</strong> Amplitude multiplier (0.3 to 2.0). 1.0 = normal volume.</p>
            <p><strong>Intensity:</strong> Chatterbox emotion exaggeration (0.0 to 1.0). Higher = more expressive.</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
