import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, RotateCcw, Volume2, Gauge, Music, Zap, Plus, Trash2, RefreshCw, Play, Pause, Upload, Server, Mic, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { apiRequest } from "@/lib/queryClient";
import { TTS_ENGINES, isVoiceCloningEngine } from "@/lib/tts-engines";
import type { TTSEngine, LibraryVoice, EdgeVoice } from "@shared/schema";
import { useAuth } from "@/lib/auth";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ProsodySettings {
  pitch: Record<string, number>;
  speed: Record<string, number>;
  volume: Record<string, number>;
  intensity: Record<string, number>;
  emotions: string[];
}

interface RegisteredEngine {
  id: string;
  engine_id: string;
  engine_name: string;
  base_url: string;
  has_api_key: boolean;
  sample_rate: number;
  bit_depth: number;
  channels: number;
  max_seconds_per_conversion: number;
  supports_voice_cloning: boolean;
  builtin_voices: Array<{ id: string; display_name: string; extra_info?: string }>;
  supported_emotions: string[];
  last_tested_at: string | null;
  last_test_success: boolean | null;
  created_at: string | null;
  user_id: string | null;
  is_shared: boolean;
}

interface VoiceLibraryItem {
  id: string;
  name: string;
  gender: string;
  age: number;
  language: string;
  location: string;
  transcript: string | null;
  duration: number;
  audioUrl: string;
  altAudioUrl: string | null;
  hasAudio: boolean;
  hasAltAudio: boolean;
}

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

interface CustomVoiceEntry {
  id: string;
  name: string;
  duration: number;
  audioUrl: string;
  createdAt: string;
}

function CustomVoicesCard() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const { data: customVoices = [], isLoading, isError } = useQuery<CustomVoiceEntry[]>({
    queryKey: ["/api/custom-voices"],
  });

  const uploadMutation = useMutation({
    mutationFn: async ({ name, file }: { name: string; file: File }) => {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("file", file);
      const res = await fetch("/api/voices/upload", { method: "POST", body: formData });
      if (!res.ok) throw new Error("Upload failed");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/custom-voices"] });
      queryClient.invalidateQueries({ queryKey: ["/api/voices"] });
      setIsDialogOpen(false);
      setNewName("");
      setSelectedFile(null);
      toast({ title: "Voice uploaded", description: "Custom voice saved successfully." });
    },
    onError: () => {
      toast({ title: "Upload failed", description: "Could not upload the voice sample.", variant: "destructive" });
    },
  });

  const renameMutation = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => {
      const formData = new FormData();
      formData.append("name", name);
      const res = await fetch(`/api/custom-voices/${id}`, { method: "PUT", body: formData });
      if (!res.ok) throw new Error("Rename failed");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/custom-voices"] });
      queryClient.invalidateQueries({ queryKey: ["/api/voices"] });
      setEditingId(null);
      toast({ title: "Voice renamed" });
    },
    onError: () => {
      toast({ title: "Rename failed", description: "Could not rename the voice.", variant: "destructive" });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await apiRequest("DELETE", `/api/voices/${id}`);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/custom-voices"] });
      queryClient.invalidateQueries({ queryKey: ["/api/voices"] });
      toast({ title: "Voice deleted" });
    },
    onError: () => {
      toast({ title: "Delete failed", description: "Could not delete the voice.", variant: "destructive" });
    },
  });

  const togglePlay = (voice: CustomVoiceEntry) => {
    if (playingId === voice.id) {
      audioRef.current?.pause();
      setPlayingId(null);
    } else {
      if (audioRef.current) audioRef.current.pause();
      audioRef.current = new Audio(voice.audioUrl);
      audioRef.current.onended = () => setPlayingId(null);
      audioRef.current.onerror = () => setPlayingId(null);
      audioRef.current.play().catch(() => setPlayingId(null));
      setPlayingId(voice.id);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Mic className="h-5 w-5" />
              Custom Voices
            </CardTitle>
            <CardDescription>
              Upload and manage custom voice samples for voice cloning
            </CardDescription>
          </div>
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" data-testid="button-add-custom-voice">
                <Plus className="h-4 w-4 mr-2" />
                Upload Voice
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Upload Custom Voice</DialogTitle>
                <DialogDescription>
                  Upload a 7-20 second audio clip for voice cloning. Clear recordings work best.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="custom-voice-name">Voice Name</Label>
                  <Input
                    id="custom-voice-name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g., Deep Narrator, Female Lead"
                    data-testid="input-custom-voice-name"
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Audio File</Label>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="audio/*"
                    className="hidden"
                    onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                    data-testid="input-custom-voice-file"
                  />
                  <Button
                    variant="outline"
                    className="w-full justify-start"
                    onClick={() => fileInputRef.current?.click()}
                    data-testid="button-select-custom-voice-file"
                  >
                    <Upload className="h-4 w-4 mr-2" />
                    {selectedFile ? selectedFile.name : "Select audio file..."}
                  </Button>
                </div>
              </div>
              <DialogFooter>
                <Button
                  onClick={() => {
                    if (selectedFile && newName.trim()) {
                      uploadMutation.mutate({ name: newName.trim(), file: selectedFile });
                    }
                  }}
                  disabled={!selectedFile || !newName.trim() || uploadMutation.isPending}
                  data-testid="button-upload-custom-voice"
                >
                  {uploadMutation.isPending ? "Uploading..." : "Upload Voice"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-center py-8 text-muted-foreground">
            <div className="animate-pulse">Loading custom voices...</div>
          </div>
        ) : isError ? (
          <div className="text-center py-8 text-muted-foreground">
            <p className="text-sm text-destructive">Failed to load custom voices</p>
          </div>
        ) : customVoices.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Volume2 className="h-10 w-10 mx-auto mb-3 opacity-50" />
            <p className="text-sm">No custom voices yet</p>
            <p className="text-xs mt-1">Upload a voice sample to get started with voice cloning</p>
          </div>
        ) : (
          <ScrollArea className={customVoices.length > 5 ? "h-[300px]" : ""}>
            <div className="space-y-2">
              {customVoices.map((voice) => (
                <div
                  key={voice.id}
                  className="flex items-center gap-3 p-3 rounded-md border bg-muted/50"
                  data-testid={`custom-voice-${voice.id}`}
                >
                  <Button
                    variant="ghost"
                    size="icon"
                    className="shrink-0"
                    onClick={() => togglePlay(voice)}
                    data-testid={`button-play-custom-${voice.id}`}
                  >
                    {playingId === voice.id ? (
                      <Pause className="h-4 w-4" />
                    ) : (
                      <Play className="h-4 w-4" />
                    )}
                  </Button>
                  <div className="flex-1 min-w-0">
                    {editingId === voice.id ? (
                      <div className="flex items-center gap-2">
                        <Input
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="h-7 text-sm"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && editName.trim()) {
                              renameMutation.mutate({ id: voice.id, name: editName.trim() });
                            }
                            if (e.key === "Escape") setEditingId(null);
                          }}
                          data-testid={`input-rename-custom-${voice.id}`}
                        />
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            if (editName.trim()) renameMutation.mutate({ id: voice.id, name: editName.trim() });
                          }}
                          data-testid={`button-save-rename-${voice.id}`}
                        >
                          <Save className="h-3 w-3" />
                        </Button>
                      </div>
                    ) : (
                      <>
                        <p className="font-medium truncate text-sm" data-testid={`text-custom-voice-name-${voice.id}`}>
                          {voice.name}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {formatDuration(voice.duration)}
                        </p>
                      </>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="shrink-0"
                    onClick={() => {
                      setEditingId(voice.id);
                      setEditName(voice.name);
                    }}
                    data-testid={`button-rename-custom-${voice.id}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="shrink-0 text-destructive"
                    onClick={() => deleteMutation.mutate(voice.id)}
                    disabled={deleteMutation.isPending}
                    data-testid={`button-delete-custom-${voice.id}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}

export function SettingsTab() {
  const { user } = useAuth();
  const isAdmin = user?.userType === "administrator";
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

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
  const [localProsody, setLocalProsody] = useState<ProsodySettings | null>(null);

  const [engineUrl, setEngineUrl] = useState("");
  const [engineApiKey, setEngineApiKey] = useState("");
  const [shareEngine, setShareEngine] = useState(false);
  const [testingEngineId, setTestingEngineId] = useState<string | null>(null);
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);

  const [parsingPromptText, setParsingPromptText] = useState("");
  const [parsingPromptLoaded, setParsingPromptLoaded] = useState(false);


  const { data: prosodyData } = useQuery<ProsodySettings>({
    queryKey: ["/api/prosody-settings"],
  });

  const { data: edgeVoicesData } = useQuery<{ voices: EdgeVoice[] }>({
    queryKey: ["/api/edge-voices"],
    enabled: defaultEngine === "edge-tts",
  });

  const showVoiceCloningOptions = isVoiceCloningEngine(defaultEngine as TTSEngine);
  
  const { data: libraryVoicesData } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library"],
    enabled: showVoiceCloningOptions,
  });

  const { data: registeredEngines, isLoading: enginesLoading } = useQuery<RegisteredEngine[]>({
    queryKey: ["/api/tts-engines"],
  });

  const { data: voiceLibraryDb, isLoading: voiceLibLoading } = useQuery<VoiceLibraryItem[]>({
    queryKey: ["/api/voice-library-db"],
  });

  const { data: savedPromptData } = useQuery<{ prompt: string }>({
    queryKey: ["/api/parsing-prompt"],
  });

  useEffect(() => {
    if (!parsingPromptLoaded && savedPromptData) {
      setParsingPromptText(savedPromptData.prompt || "");
      setParsingPromptLoaded(true);
    }
  }, [savedPromptData, parsingPromptLoaded]);

  const saveParsingPromptMutation = useMutation({
    mutationFn: async (prompt: string) => {
      const response = await apiRequest("POST", "/api/parsing-prompt", { prompt });
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/parsing-prompt"] });
      toast({ title: "Parsing prompt saved", description: "Changes will take effect on the next text analysis." });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to save prompt", description: error.message, variant: "destructive" });
    },
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

  const addEngineMutation = useMutation({
    mutationFn: async (data: { url: string; api_key?: string; is_shared?: boolean }) => {
      const response = await apiRequest("POST", "/api/tts-engines", data);
      return response.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["/api/tts-engines"] });
      setEngineUrl("");
      setEngineApiKey("");
      setShareEngine(false);
      toast({ title: "Engine registered", description: `${data.engine_name} (${data.status})` });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to add engine", description: error.message, variant: "destructive" });
    },
  });

  const testEngineMutation = useMutation({
    mutationFn: async (engineId: string) => {
      setTestingEngineId(engineId);
      const response = await apiRequest("POST", `/api/tts-engines/${engineId}/test`);
      return response.json();
    },
    onSuccess: (data) => {
      setTestingEngineId(null);
      queryClient.invalidateQueries({ queryKey: ["/api/tts-engines"] });
      if (data.success) {
        toast({ title: "Engine online", description: `${data.engine_name} - ${data.voices} voices available` });
      } else {
        toast({ title: "Engine offline", description: data.error, variant: "destructive" });
      }
    },
    onError: (error: Error) => {
      setTestingEngineId(null);
      toast({ title: "Test failed", description: error.message, variant: "destructive" });
    },
  });

  const removeEngineMutation = useMutation({
    mutationFn: async (engineId: string) => {
      const response = await apiRequest("DELETE", `/api/tts-engines/${engineId}`);
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/tts-engines"] });
      toast({ title: "Engine removed" });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to remove", description: error.message, variant: "destructive" });
    },
  });

  const uploadVoiceMutation = useMutation({
    mutationFn: async (formData: FormData) => {
      const response = await fetch("/api/voice-library-db", { method: "POST", body: formData });
      if (!response.ok) throw new Error("Upload failed");
      return response.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["/api/voice-library-db"] });
      toast({ title: "Voice uploaded", description: `${data.name} (${data.duration?.toFixed(1)}s)` });
    },
    onError: (error: Error) => {
      toast({ title: "Upload failed", description: error.message, variant: "destructive" });
    },
  });

  const deleteVoiceMutation = useMutation({
    mutationFn: async (voiceId: string) => {
      const response = await apiRequest("DELETE", `/api/voice-library-db/${voiceId}`);
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/voice-library-db"] });
      toast({ title: "Voice removed" });
    },
    onError: (error: Error) => {
      toast({ title: "Failed to remove", description: error.message, variant: "destructive" });
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

  const handleAddEngine = () => {
    if (!engineUrl.trim()) {
      toast({ title: "URL required", description: "Enter the engine endpoint URL", variant: "destructive" });
      return;
    }
    addEngineMutation.mutate({ url: engineUrl.trim(), api_key: engineApiKey.trim() || undefined, is_shared: shareEngine });
  };

  const handleVoiceUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const name = file.name.replace(/\.\w+$/, "").replace(/[_-]/g, " ");
    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", name);
    formData.append("gender", "M");
    formData.append("age", "0");
    formData.append("language", "");
    formData.append("location", "");
    formData.append("transcript", "");
    uploadVoiceMutation.mutate(formData);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handlePlayVoice = (voiceId: string, audioUrl: string) => {
    if (playingVoiceId === voiceId) {
      setPlayingVoiceId(null);
      return;
    }
    setPlayingVoiceId(voiceId);
    const audio = new Audio(audioUrl);
    audio.onended = () => setPlayingVoiceId(null);
    audio.onerror = () => setPlayingVoiceId(null);
    audio.play().catch(() => setPlayingVoiceId(null));
  };

  const getVoiceOptions = () => {
    if (defaultEngine === "edge-tts" && edgeVoicesData?.voices) {
      return edgeVoicesData.voices.map((v) => ({
        value: `edge:${v.id}`,
        label: `${v.name} (${v.gender})`,
      }));
    }
    if (showVoiceCloningOptions && libraryVoicesData) {
      return libraryVoicesData.map((v) => ({
        value: `library:${v.id}`,
        label: v.name,
      }));
    }
    const remoteEngine = registeredEngines?.find(e => e.engine_id === defaultEngine);
    if (remoteEngine) {
      if (remoteEngine.builtin_voices.length > 0) {
        return remoteEngine.builtin_voices.map((v: any) => ({
          value: v.id || v.name,
          label: v.name || v.id,
        }));
      }
      return [{ value: "default", label: "Default" }];
    }
    return [{ value: "default", label: "Default" }];
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
                    <SelectItem key={engine.id} value={engine.id}>
                      {engine.label}
                    </SelectItem>
                  ))}
                  {registeredEngines?.map((engine) => (
                    <SelectItem key={`remote-${engine.engine_id}`} value={engine.engine_id}>
                      {engine.engine_name}
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
                  <SelectValue placeholder="Select voice" />
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
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                TTS Engine Management
              </CardTitle>
              <CardDescription>
                Register and manage external TTS engines using the VoxLibris API contract
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2 items-end flex-wrap">
            <div className="flex-1 min-w-[200px] space-y-1">
              <Label htmlFor="engine-url">Engine URL</Label>
              <Input
                id="engine-url"
                placeholder="https://your-engine.hf.space"
                value={engineUrl}
                onChange={(e) => setEngineUrl(e.target.value)}
                data-testid="input-engine-url"
              />
            </div>
            <div className="w-[200px] space-y-1">
              <Label htmlFor="engine-api-key">API Key (optional)</Label>
              <Input
                id="engine-api-key"
                type="password"
                placeholder="Bearer token"
                value={engineApiKey}
                onChange={(e) => setEngineApiKey(e.target.value)}
                data-testid="input-engine-api-key"
              />
            </div>
            <Button
              onClick={handleAddEngine}
              disabled={addEngineMutation.isPending || !engineUrl.trim()}
              data-testid="button-add-engine"
            >
              <Plus className="h-4 w-4 mr-1" />
              {addEngineMutation.isPending ? "Connecting..." : "Add Engine"}
            </Button>
          </div>
          {isAdmin && (
            <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="label-share-engine">
              <input
                type="checkbox"
                checked={shareEngine}
                onChange={(e) => setShareEngine(e.target.checked)}
                className="rounded border-border"
                data-testid="checkbox-share-engine"
              />
              Share this engine with all users
            </label>
          )}

          {enginesLoading && (
            <p className="text-sm text-muted-foreground">Loading engines...</p>
          )}

          {registeredEngines && registeredEngines.length > 0 && (
            <div className="rounded-md border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Engine</TableHead>
                    <TableHead>URL</TableHead>
                    <TableHead className="text-center">Voices</TableHead>
                    <TableHead className="text-center">Cloning</TableHead>
                    <TableHead className="text-center">Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {registeredEngines.map((engine) => (
                    <TableRow key={engine.id} data-testid={`row-engine-${engine.engine_id}`}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{engine.engine_name}</span>
                          {engine.is_shared ? (
                            <Badge variant="outline" className="text-xs">Shared</Badge>
                          ) : (
                            <Badge variant="secondary" className="text-xs">Private</Badge>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground">{engine.engine_id}</div>
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                        {engine.base_url}
                      </TableCell>
                      <TableCell className="text-center">
                        {engine.builtin_voices.length}
                      </TableCell>
                      <TableCell className="text-center">
                        {engine.supports_voice_cloning ? (
                          <Badge variant="default">Yes</Badge>
                        ) : (
                          <Badge variant="secondary">No</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {engine.last_test_success === true && (
                          <Badge variant="default">Online</Badge>
                        )}
                        {engine.last_test_success === false && (
                          <Badge variant="destructive">Offline</Badge>
                        )}
                        {engine.last_test_success === null && (
                          <Badge variant="secondary">Unknown</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex gap-1 justify-end">
                          <Button
                            size="icon"
                            variant="ghost"
                            onClick={() => testEngineMutation.mutate(engine.engine_id)}
                            disabled={testingEngineId === engine.engine_id}
                            data-testid={`button-test-engine-${engine.engine_id}`}
                          >
                            <RefreshCw className={`h-4 w-4 ${testingEngineId === engine.engine_id ? "animate-spin" : ""}`} />
                          </Button>
                          {(isAdmin || engine.user_id === user?.id) && (
                            <Button
                              size="icon"
                              variant="ghost"
                              onClick={() => removeEngineMutation.mutate(engine.engine_id)}
                              disabled={removeEngineMutation.isPending}
                              data-testid={`button-remove-engine-${engine.engine_id}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {registeredEngines && registeredEngines.length === 0 && !enginesLoading && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No external TTS engines registered. Add one above using its URL.
            </p>
          )}
        </CardContent>
      </Card>

      <CustomVoicesCard />

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Mic className="h-5 w-5" />
                Voice Library
              </CardTitle>
              <CardDescription>
                Manage voice samples stored in the database for voice cloning
              </CardDescription>
            </div>
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".wav,.mp3,.ogg,.flac"
                className="hidden"
                onChange={handleVoiceUpload}
                data-testid="input-voice-upload"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadVoiceMutation.isPending}
                data-testid="button-upload-voice"
              >
                <Upload className="h-4 w-4 mr-1" />
                {uploadVoiceMutation.isPending ? "Uploading..." : "Upload Voice"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {voiceLibLoading && (
            <p className="text-sm text-muted-foreground">Loading voice library...</p>
          )}

          {voiceLibraryDb && voiceLibraryDb.length > 0 && (
            <div className="rounded-md border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead className="text-center">Gender</TableHead>
                    <TableHead className="text-center">Duration</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {voiceLibraryDb.map((voice) => (
                    <TableRow key={voice.id} data-testid={`row-voice-${voice.id}`}>
                      <TableCell>
                        <div className="font-medium">{voice.name}</div>
                        {voice.language && (
                          <div className="text-xs text-muted-foreground">
                            {voice.language}{voice.location ? ` - ${voice.location}` : ""}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        <Badge variant="secondary">{voice.gender}</Badge>
                      </TableCell>
                      <TableCell className="text-center text-sm text-muted-foreground">
                        {voice.duration > 0 ? `${voice.duration.toFixed(1)}s` : "-"}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex gap-1 justify-end">
                          {voice.hasAudio && (
                            <Button
                              size="icon"
                              variant="ghost"
                              onClick={() => handlePlayVoice(voice.id, voice.audioUrl)}
                              data-testid={`button-play-voice-${voice.id}`}
                            >
                              <Play className={`h-4 w-4 ${playingVoiceId === voice.id ? "text-primary" : ""}`} />
                            </Button>
                          )}
                          <Button
                            size="icon"
                            variant="ghost"
                            onClick={() => deleteVoiceMutation.mutate(voice.id)}
                            disabled={deleteVoiceMutation.isPending}
                            data-testid={`button-delete-voice-${voice.id}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {voiceLibraryDb && voiceLibraryDb.length === 0 && !voiceLibLoading && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No voice samples in the database. Upload a .wav file or run the migration script to import from the voice_samples folder.
            </p>
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

      {isAdmin && <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <CardTitle>Parsing & Speaker Identification Prompt</CardTitle>
              <CardDescription>
                Customize the system prompt used by the LLM for text chunking, speaker identification, and emotion assignment
              </CardDescription>
            </div>
            <Button
              size="sm"
              onClick={() => {
                if (!parsingPromptText.trim()) {
                  toast({ title: "Prompt cannot be empty", variant: "destructive" });
                  return;
                }
                saveParsingPromptMutation.mutate(parsingPromptText);
              }}
              disabled={saveParsingPromptMutation.isPending || !parsingPromptLoaded}
              data-testid="button-save-parsing-prompt"
            >
              <Save className="h-4 w-4 mr-1" />
              Save
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <textarea
            className="w-full min-h-[400px] p-3 rounded-md border bg-background text-sm font-mono resize-y focus:outline-none focus:ring-2 focus:ring-ring"
            value={parsingPromptText}
            onChange={(e) => setParsingPromptText(e.target.value)}
            placeholder="Loading prompt..."
            data-testid="textarea-parsing-prompt"
          />
          <div className="mt-3 text-sm text-muted-foreground space-y-1">
            <p>This prompt controls how the LLM segments text into chunks, identifies speakers in dialogue, and assigns emotions. Changes take effect on the next text analysis.</p>
            <p>Use <code className="text-xs bg-muted px-1 py-0.5 rounded">$&#123;VALID_EMOTIONS&#125;</code> in the prompt to automatically insert the list of available emotions.</p>
          </div>
        </CardContent>
      </Card>}
    </div>
  );
}
