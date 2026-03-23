import { useState, useCallback, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, BookOpen, Users, Volume2, Wand2, Loader2, CheckCircle, AlertCircle, Sparkles } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { TTS_ENGINES, isVoiceCloningEngine } from "@/lib/tts-engines";
import { LLM_MODELS, DEFAULT_MODEL } from "@/lib/models";
import { voiceLabel } from "@/lib/voice-label";
import { VoiceSelectOptions } from "@/components/VoiceSelectOptions";
import type { RegisteredEngine } from "@/components/SettingsPanel";
import type { TTSEngine, EdgeVoice, LibraryVoice, ProjectData } from "@shared/schema";

type WizardStep = "upload" | "analyzing" | "voices" | "generating";

interface ProjectWizardTabProps {
  onProjectCreated?: (projectId: string) => void;
}

export function ProjectWizardTab({ onProjectCreated }: ProjectWizardTabProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [step, setStep] = useState<WizardStep>("upload");
  const [inputMode, setInputMode] = useState<"file" | "text">("file");
  const [title, setTitle] = useState("");
  const [pastedText, setPastedText] = useState("");
  const [selectedModel, setSelectedModel] = useState(DEFAULT_MODEL.id);
  const [mergeShortChunks, setMergeShortChunks] = useState(true);
  const [ttsEngine, setTTSEngine] = useState<TTSEngine>(() => {
    const saved = localStorage.getItem("voxlibris-default-engine");
    return (saved as TTSEngine) || "edge-tts";
  });
  const [projectId, setProjectId] = useState<string | null>(null);
  const [voiceMode, setVoiceMode] = useState<"single" | "characters">("single");
  const [singleVoice, setSingleVoice] = useState<string>(() => {
    return localStorage.getItem("voxlibris-default-voice") || "edge:en-US-AriaNeural";
  });
  const [characterVoices, setCharacterVoices] = useState<Record<string, string>>({});

  useEffect(() => {
    setSingleVoice("");
    setCharacterVoices({});
  }, [ttsEngine]);

  const { data: projectData, refetch: refetchProject } = useQuery<ProjectData>({
    queryKey: ["/api/projects", projectId],
    enabled: !!projectId,
    refetchInterval: step === "analyzing" ? 2000 : false,
  });

  const { data: edgeVoicesData } = useQuery<{ voices: EdgeVoice[] }>({
    queryKey: ["/api/edge-voices"],
    enabled: ttsEngine === "edge-tts",
  });

  const { data: libraryVoices = [] } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library-db"],
    enabled: isVoiceCloningEngine(ttsEngine),
  });

  const { data: favoritesData } = useQuery<{ voice_ids: string[] }>({
    queryKey: ["/api/voice-favorites"],
  });
  const favoriteIds = new Set(favoritesData?.voice_ids ?? []);

  const { data: registeredEngines = [] } = useQuery<RegisteredEngine[]>({
    queryKey: ["/api/tts-engines"],
  });

  useEffect(() => {
    if (projectData && step === "analyzing") {
      const allChaptersSegmented = projectData.chapters?.every(
        (ch: any) => ch.status === "segmented" || ch.status === "failed"
      );
      if (projectData.status === "segmented" || allChaptersSegmented) {
        setStep("voices");
      }
    }
  }, [projectData, step]);

  const detectedSpeakers: string[] = (() => {
    if (!projectData?.speakersJson) return [];
    try {
      const parsed = JSON.parse(projectData.speakersJson);
      return Object.keys(parsed).filter(s => s !== "Narrator");
    } catch {
      return [];
    }
  })();

  const [titleError, setTitleError] = useState<string | null>(null);

  const createAndSegmentMutation = useMutation({
    mutationFn: async (fileOrNull: File | null) => {
      setTitleError(null);
      const formData = new FormData();
      formData.append("title", title.trim());
      if (inputMode === "text") {
        formData.append("text", pastedText);
      } else if (fileOrNull) {
        formData.append("file", fileOrNull);
      }

      const res = await fetch("/api/projects", {
        method: "POST",
        body: formData,
        credentials: "include",
      });
      if (!res.ok) {
        if (res.status === 409) {
          const errData = await res.json().catch(() => ({ detail: "Title already taken" }));
          throw new Error(`__TITLE_CONFLICT__${errData.detail || "A project with this title already exists"}`);
        }
        const errData = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(errData.detail || "Failed to create project");
      }
      const project = await res.json();

      const segRes = await fetch(`/api/projects/${project.id}/segment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: selectedModel, merge_short_chunks: mergeShortChunks }),
        credentials: "include",
      });
      if (!segRes.ok) {
        throw new Error("Project created but segmentation failed to start");
      }

      return project;
    },
    onSuccess: (project) => {
      setProjectId(project.id);
      setStep("analyzing");
      setTitleError(null);
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      toast({
        title: "Project created",
        description: "Analyzing text and detecting speakers...",
      });
    },
    onError: (error: Error) => {
      if (error.message.startsWith("__TITLE_CONFLICT__")) {
        setTitleError(error.message.replace("__TITLE_CONFLICT__", ""));
      } else {
        toast({
          title: "Failed to create project",
          description: error.message,
          variant: "destructive",
        });
      }
    },
  });

  const saveSettingsAndGenerateMutation = useMutation({
    mutationFn: async () => {
      if (!projectId) throw new Error("No project");

      const speakersMap: Record<string, { voiceId: string }> = {};
      if (voiceMode === "single") {
        speakersMap["Narrator"] = { voiceId: singleVoice };
      } else {
        if (characterVoices["Narrator"]) {
          speakersMap["Narrator"] = { voiceId: characterVoices["Narrator"] };
        }
        for (const speaker of detectedSpeakers) {
          if (characterVoices[speaker]) {
            speakersMap[speaker] = { voiceId: characterVoices[speaker] };
          }
        }
      }

      const settingsRes = await fetch(`/api/projects/${projectId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ttsEngine,
          narratorVoiceId: voiceMode === "single" ? singleVoice : (characterVoices["Narrator"] || singleVoice),
          speakersJson: JSON.stringify(speakersMap),
        }),
        credentials: "include",
      });
      if (!settingsRes.ok) {
        throw new Error("Failed to save voice settings");
      }

      const genRes = await fetch(`/api/projects/${projectId}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scopeType: "project", scopeId: projectId }),
        credentials: "include",
      });
      if (!genRes.ok) {
        const errData = await genRes.json().catch(() => ({ detail: "Generation failed" }));
        throw new Error(errData.detail || "Generation failed");
      }
      return genRes.json();
    },
    onSuccess: (data) => {
      setStep("generating");
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      toast({
        title: "Generation started",
        description: `Created ${data.totalJobs || data.jobCount || 1} job(s). Your audiobook is being generated.`,
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
      createAndSegmentMutation.mutate(file);
    }
  }, [createAndSegmentMutation]);

  const handleTextSubmit = useCallback(() => {
    if (!pastedText.trim()) return;
    createAndSegmentMutation.mutate(null);
  }, [createAndSegmentMutation, pastedText]);

  const handleReset = useCallback(() => {
    setStep("upload");
    setProjectId(null);
    setCharacterVoices({});
    setTitle("");
    setPastedText("");
    setInputMode("file");
    setTitleError(null);
  }, []);

  const handleViewProject = useCallback(() => {
    if (projectId && onProjectCreated) {
      onProjectCreated(projectId);
    }
  }, [projectId, onProjectCreated]);

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
        label: voiceLabel(v),
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

  const chapterProgress = projectData?.chapters
    ? {
        total: projectData.chapters.length,
        done: projectData.chapters.filter((ch: any) => ch.status === "segmented" || ch.status === "failed").length,
      }
    : { total: 0, done: 0 };
  const progress = chapterProgress.total > 0 ? Math.round((chapterProgress.done / chapterProgress.total) * 100) : 0;

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
              <Sparkles className="h-5 w-5" />
              Create a New Audiobook
            </CardTitle>
            <CardDescription>
              Upload a file or paste text, then we'll analyze it and help you assign voices
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="wizard-title">Project Title</Label>
              <Input
                id="wizard-title"
                data-testid="input-wizard-title"
                value={title}
                onChange={(e) => { setTitle(e.target.value); setTitleError(null); }}
                placeholder="(Use Default Title)"
                className={titleError ? "border-destructive" : ""}
              />
              {titleError && (
                <p className="text-xs text-destructive" data-testid="text-wizard-title-error">{titleError}</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Button
                variant={inputMode === "file" ? "default" : "outline"}
                onClick={() => setInputMode("file")}
                data-testid="button-input-file"
              >
                <Upload className="h-4 w-4 mr-2" />
                Upload File
              </Button>
              <Button
                variant={inputMode === "text" ? "default" : "outline"}
                onClick={() => setInputMode("text")}
                data-testid="button-input-text"
              >
                <FileText className="h-4 w-4 mr-2" />
                Paste Text
              </Button>
            </div>

            {inputMode === "file" && (
              <div
                className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
                onClick={() => document.getElementById("wizard-file-upload")?.click()}
                data-testid="dropzone-upload"
              >
                <input
                  id="wizard-file-upload"
                  type="file"
                  accept=".txt,.epub"
                  className="hidden"
                  onChange={handleFileSelect}
                  disabled={createAndSegmentMutation.isPending}
                />
                {createAndSegmentMutation.isPending ? (
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="h-10 w-10 animate-spin text-primary" />
                    <p className="text-sm text-muted-foreground">Creating project...</p>
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
            )}

            {inputMode === "text" && (
              <div className="space-y-2">
                <Textarea
                  data-testid="input-wizard-text"
                  value={pastedText}
                  onChange={(e) => setPastedText(e.target.value)}
                  placeholder="Paste your book text here..."
                  rows={8}
                  className="font-mono text-sm"
                />
                <div className="flex items-center justify-between">
                  <p className="text-xs text-muted-foreground">
                    {pastedText.split(/\s+/).filter(Boolean).length} words
                  </p>
                  <Button
                    onClick={handleTextSubmit}
                    disabled={!pastedText.trim() || createAndSegmentMutation.isPending}
                    data-testid="button-submit-text"
                  >
                    {createAndSegmentMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : null}
                    Create & Analyze
                  </Button>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>TTS Engine</Label>
                <Select value={ttsEngine} onValueChange={(v) => setTTSEngine(v as TTSEngine)}>
                  <SelectTrigger data-testid="select-tts-engine-wizard">
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

              <div className="space-y-2">
                <Label>Analysis Model</Label>
                <Select value={selectedModel} onValueChange={setSelectedModel}>
                  <SelectTrigger data-testid="select-model-wizard">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {LLM_MODELS.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={mergeShortChunks}
                onCheckedChange={(v) => setMergeShortChunks(!!v)}
              />
              Merge short / punctuation-only chunks after segmentation
            </label>
          </CardContent>
        </Card>
      )}

      {step === "analyzing" && projectData && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Loader2 className="h-5 w-5 animate-spin" />
              Analyzing Text
            </CardTitle>
            <CardDescription>
              Detecting speakers and analyzing "{projectData.title}"
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Progress value={progress} className="h-2" />
            <p className="text-sm text-muted-foreground text-center">
              {chapterProgress.done} of {chapterProgress.total} chapter(s) analyzed
            </p>

            {projectData.chapters && (
              <div className="space-y-2">
                {projectData.chapters.map((chapter: any) => (
                  <div
                    key={chapter.id}
                    className="flex items-center justify-between p-2 rounded bg-muted/50"
                  >
                    <span className="text-sm">{chapter.title}</span>
                    {chapter.status === "segmented" ? (
                      <CheckCircle className="h-4 w-4 text-green-500" />
                    ) : chapter.status === "failed" ? (
                      <AlertCircle className="h-4 w-4 text-destructive" />
                    ) : (
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {step === "voices" && (
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
            <div className="space-y-2">
              <Label>TTS Engine</Label>
              <Select value={ttsEngine} onValueChange={(v) => setTTSEngine(v as TTSEngine)}>
                <SelectTrigger data-testid="select-tts-engine-voices">
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
                disabled={detectedSpeakers.length === 0}
                data-testid="button-character-voices"
              >
                <Users className="h-4 w-4 mr-2" />
                Character Voices
                {detectedSpeakers.length > 0 && (
                  <Badge variant="secondary" className="ml-2">{detectedSpeakers.length}</Badge>
                )}
              </Button>
            </div>

            {voiceMode === "single" && (
              <div className="space-y-2">
                <Label>Voice</Label>
                <Select value={singleVoice} onValueChange={setSingleVoice}>
                  <SelectTrigger data-testid="select-single-voice">
                    <SelectValue placeholder="Select a voice" />
                  </SelectTrigger>
                  <SelectContent>
                    <VoiceSelectOptions opts={voiceOptions} favoriteIds={favoriteIds} />
                  </SelectContent>
                </Select>
              </div>
            )}

            {voiceMode === "characters" && detectedSpeakers.length > 0 && (
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label>Narrator Voice</Label>
                  <Select
                    value={characterVoices["Narrator"] || ""}
                    onValueChange={(v) => setCharacterVoices((prev) => ({ ...prev, Narrator: v }))}
                  >
                    <SelectTrigger data-testid="select-narrator-voice">
                      <SelectValue placeholder="Select narrator voice" />
                    </SelectTrigger>
                    <SelectContent>
                      <VoiceSelectOptions opts={voiceOptions} favoriteIds={favoriteIds} />
                    </SelectContent>
                  </Select>
                </div>

                {detectedSpeakers.map((speaker) => (
                  <div key={speaker} className="space-y-2">
                    <Label>{speaker}</Label>
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
                        <VoiceSelectOptions opts={voiceOptions} favoriteIds={favoriteIds} />
                      </SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            )}

            <div className="pt-4">
              <Button
                onClick={() => saveSettingsAndGenerateMutation.mutate()}
                disabled={saveSettingsAndGenerateMutation.isPending}
                className="w-full gap-2"
                data-testid="button-generate-audiobook"
              >
                {saveSettingsAndGenerateMutation.isPending ? (
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
              Your project has been created and audio generation is underway. You can view the project to track progress and play audio as it's generated.
            </p>
            <div className="flex gap-2">
              <Button onClick={handleViewProject} className="flex-1" data-testid="button-view-project">
                <BookOpen className="h-4 w-4 mr-2" />
                View Project
              </Button>
              <Button onClick={handleReset} variant="outline" className="flex-1" data-testid="button-create-another">
                <Sparkles className="h-4 w-4 mr-2" />
                Create Another
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
