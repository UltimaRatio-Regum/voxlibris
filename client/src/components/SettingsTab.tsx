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
  { value: "chatterbox-paid", label: "Chatterbox Paid" },
  { value: "piper", label: "Piper TTS" },
  { value: "soprano", label: "Soprano TTS" },
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
    localStorage.getItem("narrator-default-engine") || "edge-tts"
  );
  const [defaultVoice, setDefaultVoice] = useState(() =>
    localStorage.getItem("narrator-default-voice") || ""
  );
  const [localProsody, setLocalProsody] = useState<ProsodySettings | null>(null);

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

  const { data: libraryVoicesData } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library"],
    enabled: defaultEngine === "chatterbox-free" || defaultEngine === "chatterbox-paid",
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
    localStorage.setItem("narrator-default-engine", engine);
    localStorage.removeItem("narrator-default-voice");
  };

  const handleVoiceChange = (voice: string) => {
    setDefaultVoice(voice);
    localStorage.setItem("narrator-default-voice", voice);
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
      return edgeVoicesData.voices.slice(0, 50).map((v) => ({
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
    if ((defaultEngine === "chatterbox-free" || defaultEngine === "chatterbox-paid") && libraryVoicesData) {
      return libraryVoicesData.slice(0, 50).map((v) => ({
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
