import { useState, useCallback, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, BookOpen, Users, Volume2, Wand2, Loader2, CheckCircle, AlertCircle, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import { TTS_ENGINES, isVoiceCloningEngine } from "@/lib/tts-engines";
import type { RegisteredEngine } from "@/components/SettingsPanel";
import type { TTSEngine, EdgeVoice, LibraryVoice } from "@shared/schema";

interface Upload {
  id: string;
  filename: string;
  filetype: string;
  status: string;
  ttsEngine: string;
  totalChapters: number;
  analyzedChapters: number;
  chapters: {
    id: string;
    index: number;
    title: string;
    status: string;
    hasAnalysis: boolean;
  }[];
  detectedSpeakers: string[];
}

type WizardStep = "upload" | "analyzing" | "voices" | "generating";

export function BeginnerTab() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<WizardStep>("upload");
  const [ttsEngine, setTTSEngine] = useState<TTSEngine>(() => {
    const saved = localStorage.getItem("voxlibris-default-engine");
    return (saved as TTSEngine) || "edge-tts";
  });
  const [currentUploadId, setCurrentUploadId] = useState<string | null>(null);
  const [voiceMode, setVoiceMode] = useState<"single" | "characters">("single");
  const [singleVoice, setSingleVoice] = useState<string>(() => {
    return localStorage.getItem("voxlibris-default-voice") || "edge:en-US-AriaNeural";
  });
  const [characterVoices, setCharacterVoices] = useState<Record<string, string>>({});

  const { data: currentUpload, refetch: refetchUpload } = useQuery<Upload>({
    queryKey: ["/api/uploads", currentUploadId],
    queryFn: async () => {
      if (!currentUploadId) return null;
      const response = await fetch(`/api/uploads/${currentUploadId}`);
      return response.json();
    },
    enabled: !!currentUploadId,
    refetchInterval: step === "analyzing" ? 2000 : false,
  });

  const { data: edgeVoicesData } = useQuery<{ voices: EdgeVoice[] }>({
    queryKey: ["/api/edge-voices"],
    enabled: ttsEngine === "edge-tts",
  });

  const { data: libraryVoices = [] } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library"],
    enabled: isVoiceCloningEngine(ttsEngine),
  });

  const { data: registeredEngines = [] } = useQuery<RegisteredEngine[]>({
    queryKey: ["/api/tts-engines"],
  });

  useEffect(() => {
    if (currentUpload?.status === "analyzed" && step === "analyzing") {
      setStep("voices");
    }
  }, [currentUpload?.status, step]);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("tts_engine", ttsEngine);
      
      const response = await fetch("/api/uploads", {
        method: "POST",
        body: formData,
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Upload failed");
      }
      
      return response.json();
    },
    onSuccess: async (data) => {
      setCurrentUploadId(data.uploadId);
      setStep("analyzing");
      
      await apiRequest("POST", `/api/uploads/${data.uploadId}/analyze`);
      
      toast({
        title: "File uploaded",
        description: `Processing ${data.totalChapters} chapter(s)...`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Upload failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const generateMutation = useMutation({
    mutationFn: async () => {
      if (!currentUploadId) throw new Error("No upload selected");
      
      const response = await apiRequest("POST", `/api/uploads/${currentUploadId}/generate`, {
        singleVoice: voiceMode === "single" ? singleVoice : null,
        voiceAssignments: voiceMode === "characters" ? characterVoices : {},
      });
      
      return response.json();
    },
    onSuccess: (data) => {
      setStep("generating");
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
      toast({
        title: "Generation started",
        description: `Created ${data.count} job(s). Check the Job Monitor tab for progress.`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Generation failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate(file);
    }
  }, [uploadMutation]);

  const handleReset = useCallback(() => {
    setStep("upload");
    setCurrentUploadId(null);
    setCharacterVoices({});
  }, []);

  const getVoiceOptions = () => {
    if (ttsEngine === "edge-tts" && edgeVoicesData?.voices) {
      return edgeVoicesData.voices.map(v => ({
        value: `edge:${v.id}`,
        label: `${v.name} (${v.gender})`,
      }));
    }
    if (isVoiceCloningEngine(ttsEngine) && libraryVoices) {
      return libraryVoices.map(v => ({
        value: `library:${v.id}`,
        label: v.name,
      }));
    }
    const registeredEngine = registeredEngines.find(e => e.engine_id === ttsEngine);
    if (registeredEngine?.builtin_voices?.length) {
      return registeredEngine.builtin_voices.map(v => ({
        value: `remote:${v.id}`,
        label: v.display_name,
      }));
    }
    return [{ value: "default", label: "Default Voice" }];
  };

  const voiceOptions = getVoiceOptions();
  const progress = currentUpload 
    ? Math.round((currentUpload.analyzedChapters / currentUpload.totalChapters) * 100)
    : 0;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {["upload", "analyzing", "voices", "generating"].map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  step === s
                    ? "bg-primary text-primary-foreground"
                    : ["upload", "analyzing", "voices", "generating"].indexOf(step) > i
                    ? "bg-primary/20 text-primary"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {i + 1}
              </div>
              {i < 3 && <div className="w-8 h-0.5 bg-muted" />}
            </div>
          ))}
        </div>
        {step !== "upload" && (
          <Button variant="ghost" size="sm" onClick={handleReset} data-testid="button-reset-wizard">
            Start Over
          </Button>
        )}
      </div>

      {step === "upload" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5" />
              Upload Your Book
            </CardTitle>
            <CardDescription>
              Upload a .txt or .epub file to convert to an audiobook
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">TTS Engine</label>
              <Select value={ttsEngine} onValueChange={(v) => setTTSEngine(v as TTSEngine)}>
                <SelectTrigger data-testid="select-tts-engine-beginner">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TTS_ENGINES.map((engine) => (
                    <SelectItem key={engine.id} value={engine.id}>
                      {engine.label}
                    </SelectItem>
                  ))}
                  {registeredEngines.map((engine) => (
                    <SelectItem key={engine.engine_id} value={engine.engine_id}>
                      {engine.engine_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div
              className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover-elevate transition-colors"
              onClick={() => document.getElementById("file-upload")?.click()}
              data-testid="dropzone-upload"
            >
              <input
                id="file-upload"
                type="file"
                accept=".txt,.epub"
                className="hidden"
                onChange={handleFileSelect}
                disabled={uploadMutation.isPending}
              />
              {uploadMutation.isPending ? (
                <div className="flex flex-col items-center gap-2">
                  <Loader2 className="h-10 w-10 animate-spin text-primary" />
                  <p className="text-sm text-muted-foreground">Uploading...</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <div className="flex gap-4">
                    <FileText className="h-10 w-10 text-muted-foreground" />
                    <BookOpen className="h-10 w-10 text-muted-foreground" />
                  </div>
                  <p className="font-medium">Click to upload</p>
                  <p className="text-sm text-muted-foreground">
                    Supports .txt and .epub files
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {step === "analyzing" && currentUpload && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin" />
              Analyzing Text
            </CardTitle>
            <CardDescription>
              Detecting speakers and analyzing {currentUpload.filename}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={progress} className="h-2" />
            <p className="text-sm text-muted-foreground text-center">
              {currentUpload.analyzedChapters} of {currentUpload.totalChapters} chapters analyzed
            </p>
            
            <div className="space-y-2">
              {currentUpload.chapters.map((chapter) => (
                <div
                  key={chapter.id}
                  className="flex items-center justify-between p-2 rounded bg-muted/50"
                >
                  <span className="text-sm">{chapter.title}</span>
                  {chapter.status === "analyzed" ? (
                    <CheckCircle className="h-4 w-4 text-green-500" />
                  ) : chapter.status === "failed" ? (
                    <AlertCircle className="h-4 w-4 text-destructive" />
                  ) : (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {step === "voices" && currentUpload && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Assign Voices
            </CardTitle>
            <CardDescription>
              Choose how to assign voices to your audiobook
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Button
                variant={voiceMode === "single" ? "default" : "outline"}
                onClick={() => setVoiceMode("single")}
                className="flex-1"
                data-testid="button-single-voice"
              >
                <Volume2 className="h-4 w-4 mr-2" />
                Single Voice
              </Button>
              <Button
                variant={voiceMode === "characters" ? "default" : "outline"}
                onClick={() => setVoiceMode("characters")}
                className="flex-1"
                disabled={currentUpload.detectedSpeakers.length === 0}
                data-testid="button-character-voices"
              >
                <Users className="h-4 w-4 mr-2" />
                Character Voices
              </Button>
            </div>

            {voiceMode === "single" && (
              <div className="space-y-2">
                <label className="text-sm font-medium">Voice</label>
                <Select value={singleVoice} onValueChange={setSingleVoice}>
                  <SelectTrigger data-testid="select-single-voice">
                    <SelectValue placeholder="Select a voice" />
                  </SelectTrigger>
                  <SelectContent>
                    {voiceOptions.slice(0, 20).map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {voiceMode === "characters" && currentUpload.detectedSpeakers.length > 0 && (
              <div className="space-y-3">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Narrator Voice</label>
                  <Select
                    value={characterVoices["Narrator"] || ""}
                    onValueChange={(v) => setCharacterVoices((prev) => ({ ...prev, Narrator: v }))}
                  >
                    <SelectTrigger data-testid="select-narrator-voice">
                      <SelectValue placeholder="Select narrator voice" />
                    </SelectTrigger>
                    <SelectContent>
                      {voiceOptions.slice(0, 20).map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                
                {currentUpload.detectedSpeakers.map((speaker) => (
                  <div key={speaker} className="space-y-2">
                    <label className="text-sm font-medium">{speaker}</label>
                    <Select
                      value={characterVoices[speaker] || ""}
                      onValueChange={(v) =>
                        setCharacterVoices((prev) => ({ ...prev, [speaker]: v }))
                      }
                    >
                      <SelectTrigger data-testid={`select-voice-${speaker}`}>
                        <SelectValue placeholder={`Select voice for ${speaker}`} />
                      </SelectTrigger>
                      <SelectContent>
                        {voiceOptions.slice(0, 20).map((opt) => (
                          <SelectItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            )}

            <div className="pt-4">
              <Button
                onClick={() => generateMutation.mutate()}
                disabled={generateMutation.isPending}
                className="w-full gap-2"
                data-testid="button-generate-audiobook"
              >
                {generateMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Wand2 className="h-4 w-4" />
                )}
                Generate Audiobook
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "generating" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-500" />
              Generation Started
            </CardTitle>
            <CardDescription>
              Your audiobook is being generated in the background
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Switch to the <strong>Job Monitor</strong> tab to track progress and download your audiobook when ready.
            </p>
            <Button onClick={handleReset} variant="outline" className="w-full" data-testid="button-create-another">
              Create Another Audiobook
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
