import { useState, useEffect, useRef, useMemo, forwardRef, useImperativeHandle } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Wand2, Save, Book, Layers, FileText, Type, Download, Upload, X, Image, Users, AlertTriangle, RefreshCw, Merge, CheckSquare, Loader2, Clock, BookOpen, Music } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { ProjectAudioList } from "@/components/ProjectAudioList";
import { SpeakerInspectorDialog } from "@/components/SpeakerInspectorDialog";
import { TTS_ENGINES } from "@/lib/tts-engines";
import { voiceLabel } from "@/lib/voice-label";
import { VoiceSelectOptions } from "@/components/VoiceSelectOptions";
import { LLM_MODELS, DEFAULT_MODEL } from "@/lib/models";
import type { TreeSelection } from "@/components/ProjectTree";
import type {
  ProjectData,
  ProjectChapter,
  ProjectSection,
  ProjectChunk,
  ProjectAudioFile,
  VoiceSample,
  LibraryVoice,
  EdgeVoice,
  OutputFormat,
  SpeakerConfig,
  NarratorEmotion,
  DialogueEmotionMode,
} from "@shared/schema";

const CANONICAL_EMOTIONS = [
  "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
  "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
];

interface ProjectDetailPanelProps {
  selection: TreeSelection;
  project: ProjectData;
  onRefresh: () => void;
  settingsPanelRef?: React.RefObject<{ save: () => void; isDirty: () => boolean } | null>;
}

const SETTINGS_TYPES = new Set(["project", "engine-settings", "voice-settings", "characters", "output-files"]);
// Lazy imports for validation panels
import { ValidationPanel } from "@/components/ValidationPanel";
import { ValidationChunkPanel } from "@/components/ValidationChunkPanel";

export function ProjectDetailPanel({ selection, project, onRefresh, settingsPanelRef }: ProjectDetailPanelProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [onlyMissing, setOnlyMissing] = useState(false);

  const { data: voiceSamples = [] } = useQuery<VoiceSample[]>({
    queryKey: ["/api/voices"],
  });

  const { data: libraryVoices = [] } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library-db"],
  });

  const { data: favoritesData } = useQuery<{ voice_ids: string[] }>({
    queryKey: ["/api/voice-favorites"],
  });
  const favoriteIds = new Set(favoritesData?.voice_ids ?? []);

  const { data: registeredEngines = [] } = useQuery<any[]>({
    queryKey: ["/api/tts-engines"],
  });

  const { data: audioStats = {} } = useQuery<Record<string, { total: number; withAudio: number }>>({
    queryKey: ["/api/projects", project.id, "audio-stats"],
  });

  const allEngines = [
    ...TTS_ENGINES.map((e) => ({ id: e.id, label: e.label })),
    ...registeredEngines.map((e: any) => ({ id: e.engine_id || e.id, label: e.engine_name || e.name || e.engine_id || e.id })),
  ];

  const allVoices = [
    ...voiceSamples.map((v) => ({ id: v.id, label: v.name })),
    ...libraryVoices.map((v) => ({ id: `library:${v.id}`, label: voiceLabel(v) })),
  ];

  const audioFiles = useMemo(() => {
    const allAudio = project.audioFiles || [];
    let filtered: typeof allAudio;

    if (selection.type === "chunk") {
      filtered = allAudio.filter(af => af.scopeType === "chunk" && af.scopeId === selection.id);
    } else if (selection.type === "section") {
      filtered = allAudio.filter(af => af.scopeType === "section" && af.scopeId === selection.id);
      if (filtered.length === 0) {
        const section = selection.data as ProjectSection;
        const chunkIds = (section.chunks || []).map(c => c.id);
        filtered = allAudio.filter(af => af.scopeType === "chunk" && chunkIds.includes(af.scopeId));
      }
    } else if (selection.type === "chapter") {
      filtered = allAudio.filter(af => af.scopeType === "chapter" && af.scopeId === selection.id);
      if (filtered.length === 0) {
        const chapter = selection.data as ProjectChapter;
        const sectionIds = (chapter.sections || []).map(s => s.id);
        filtered = allAudio.filter(af => af.scopeType === "section" && sectionIds.includes(af.scopeId));
        const sectionOrder = new Map(sectionIds.map((id, idx) => [id, idx]));
        filtered.sort((a, b) => (sectionOrder.get(a.scopeId) ?? 0) - (sectionOrder.get(b.scopeId) ?? 0));
      }
    } else {
      filtered = [];
    }
    return filtered;
  }, [project.audioFiles, selection]);

  const generateMutation = useMutation({
    mutationFn: async () => {
      const scopeId = selection.type === "project" ? project.id : selection.id;
      const res = await apiRequest("POST", `/api/projects/${project.id}/generate`, {
        scopeType: selection.type,
        scopeId,
        onlyMissing,
      });
      return res.json();
    },
    onSuccess: (data) => {
      if (data.message) {
        toast({ title: "Nothing to generate", description: data.message });
        return;
      }
      const jobCount = data.totalJobs || 1;
      const desc = jobCount > 1
        ? `${jobCount} section jobs created with ${data.totalSegments} total segments. Check the Jobs tab for progress.`
        : `Job created with ${data.totalSegments} segments. Check the Jobs tab for progress.`;
      toast({ title: "Generation started", description: desc });
      queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id, "audio-stats"] });
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Generation failed", description: error.message, variant: "destructive" });
    },
  });

  const currentScopeId = selection.type === "project" ? project.id : selection.id;
  const currentStats = audioStats[currentScopeId];
  const hasAnyAudio = currentStats && currentStats.withAudio > 0;
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async () => {
    const scope = selection.type === "project" ? "project" : selection.type;
    const scopeId = selection.type === "project" ? "" : selection.id;
    setIsDownloading(true);
    toast({ title: "Preparing download...", description: "This may take a moment for large projects." });
    try {
      const response = await fetch(`/api/projects/${project.id}/download?scope=${scope}&scopeId=${scopeId}`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = response.headers.get("content-disposition");
      const match = disposition?.match(/filename="?(.+?)"?$/);
      a.download = match?.[1] || `${project.title || "audiobook"}.${project.outputFormat === "m4b" ? "m4b" : "mp3"}`;
      a.click();
      URL.revokeObjectURL(url);
      toast({ title: "Download complete" });
    } catch {
      toast({ title: "Download failed", description: "Could not download audio", variant: "destructive" });
    } finally {
      setIsDownloading(false);
    }
  };

  const isSettingsView = SETTINGS_TYPES.has(selection.type);

  return (
    <div className="space-y-6" data-testid="project-detail-panel">
      {/* Settings panel — always mounted when any settings view is active, uses view prop to switch sections */}
      {isSettingsView && (
        <ProjectSettingsPanel
          ref={settingsPanelRef as React.Ref<{ save: () => void; isDirty: () => boolean }> | undefined}
          project={project}
          allEngines={allEngines}
          allVoices={allVoices}
          favoriteIds={favoriteIds}
          registeredEngines={registeredEngines}
          onRefresh={onRefresh}
          view={selection.type as "project" | "engine-settings" | "voice-settings" | "characters" | "output-files"}
        />
      )}

      {selection.type === "book-content" && (
        <BookContentInfoPanel project={project} />
      )}

      {selection.type === "validation" && (
        <ValidationPanel project={project} onRefresh={onRefresh} />
      )}

      {selection.type === "validation-chunk" && (
        <ValidationChunkPanel chunkId={selection.id} project={project} onRefresh={onRefresh} />
      )}

      {selection.type === "chapter" && (
        <ChapterDetailPanel
          chapter={selection.data as ProjectChapter}
          project={project}
          allEngines={allEngines}
          allVoices={allVoices}
          favoriteIds={favoriteIds}
          onRefresh={onRefresh}
        />
      )}

      {selection.type === "section" && (
        <SectionDetailPanel section={selection.data as ProjectSection} project={project} onRefresh={onRefresh} />
      )}

      {selection.type === "chunk" && (
        <ChunkDetailPanel
          chunk={selection.data as ProjectChunk}
          project={project}
          onRefresh={onRefresh}
        />
      )}

      {/* Audio Generation section — only for chapter/section/chunk (not project level, which is in Output Files) */}
      {(selection.type === "chapter" || selection.type === "section" || selection.type === "chunk") && (
        <>
          <Separator />

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Audio Generation</h3>
              <div className="flex items-center gap-2">
                {hasAnyAudio && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleDownload}
                    disabled={isDownloading}
                    data-testid="button-download-audio"
                  >
                    {isDownloading ? (
                      <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                    ) : (
                      <Download className="h-3.5 w-3.5 mr-1" />
                    )}
                    {isDownloading ? "Downloading..." : `Download ${selection.type}`}
                    {!isDownloading && currentStats && (
                      <span className="ml-1 text-xs text-muted-foreground">
                        ({currentStats.withAudio}/{currentStats.total})
                      </span>
                    )}
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={() => generateMutation.mutate()}
                  disabled={generateMutation.isPending || project.status === "segmenting"}
                  data-testid="button-generate-audio"
                >
                  <Wand2 className="h-3.5 w-3.5 mr-1" />
                  {generateMutation.isPending ? "Starting..." : `Generate ${selection.type}`}
                </Button>
              </div>
            </div>

            {selection.type !== "chunk" && (
              <div className="flex items-center gap-2">
                <Checkbox
                  id="only-missing"
                  checked={onlyMissing}
                  onCheckedChange={(checked) => setOnlyMissing(checked === true)}
                  data-testid="checkbox-only-missing"
                />
                <label
                  htmlFor="only-missing"
                  className="text-xs text-muted-foreground cursor-pointer select-none"
                >
                  Only generate missing segments
                  {currentStats && currentStats.withAudio > 0 && (
                    <span className="ml-1">
                      ({currentStats.total - currentStats.withAudio} remaining)
                    </span>
                  )}
                </label>
              </div>
            )}

            <ProjectAudioList audioFiles={audioFiles} projectId={project.id} onDelete={onRefresh} />
          </div>
        </>
      )}
    </div>
  );
}

// ─── Book Content Info Panel ────────────────────────────────────────────────

function BookContentInfoPanel({ project }: { project: ProjectData }) {
  const chapters = project.chapters || [];
  const totalSections = chapters.reduce((sum, ch) => sum + (ch.sections?.length || 0), 0);
  const totalChunks = chapters.reduce(
    (sum, ch) => sum + (ch.sections || []).reduce((s, sec) => s + (sec.chunks?.length || 0), 0),
    0
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <BookOpen className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-bold" data-testid="text-detail-title">Book Content</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        The book content tree shows the structure of your project. Select a chapter, section, or chunk to view and edit details.
      </p>
      <div className="grid grid-cols-3 gap-4 text-center">
        <div className="rounded-lg border p-4">
          <div className="text-2xl font-bold">{chapters.length}</div>
          <div className="text-xs text-muted-foreground mt-1">Chapters</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-2xl font-bold">{totalSections}</div>
          <div className="text-xs text-muted-foreground mt-1">Sections</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-2xl font-bold">{totalChunks}</div>
          <div className="text-xs text-muted-foreground mt-1">Chunks</div>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Source type: <span className="font-medium">{project.sourceType}</span>
        {project.sourceFilename && (
          <> &mdash; <span className="font-medium">{project.sourceFilename}</span></>
        )}
      </p>
    </div>
  );
}

// ─── Project Settings Panel ──────────────────────────────────────────────────

type SettingsView = "project" | "engine-settings" | "voice-settings" | "characters" | "output-files";

interface ProjectSettingsPanelProps {
  project: ProjectData;
  allEngines: { id: string; label: string }[];
  allVoices: { id: string; label: string }[];
  favoriteIds: Set<string>;
  registeredEngines: any[];
  onRefresh: () => void;
  view: SettingsView;
}

const ProjectSettingsPanel = forwardRef<
  { save: () => void; isDirty: () => boolean },
  ProjectSettingsPanelProps
>(function ProjectSettingsPanel(
  { project, allEngines, allVoices, favoriteIds, registeredEngines, onRefresh, view },
  ref
) {
  const { toast } = useToast();
  const coverInputRef = useRef<HTMLInputElement>(null);
  const [isDirty, setIsDirty] = useState(false);

  const [ttsEngine, setTtsEngineRaw] = useState(project.ttsEngine || "edge-tts");
  const [narratorVoice, setNarratorVoiceRaw] = useState(project.narratorVoiceId || "");
  const [narratorSpeed, setNarratorSpeedRaw] = useState(project.narratorSpeed ?? 1.0);
  const [baseVoiceId, setBaseVoiceIdRaw] = useState(project.baseVoiceId || "");
  const [exaggeration, setExaggerationRaw] = useState(project.exaggeration ?? 0.5);
  const [pauseDuration, setPauseDurationRaw] = useState(project.pauseDuration ?? 150);
  const [narratorEmotion, setNarratorEmotionRaw] = useState<NarratorEmotion>(project.narratorEmotion || "auto");
  const [dialogueEmotionMode, setDialogueEmotionModeRaw] = useState<DialogueEmotionMode>(project.dialogueEmotionMode || "per-chunk");
  const [outputFormat, setOutputFormatRaw] = useState<OutputFormat>(project.outputFormat || "mp3");
  const [metaAuthor, setMetaAuthorRaw] = useState(project.metaAuthor || "");
  const [metaNarrator, setMetaNarratorRaw] = useState(project.metaNarrator || "");
  const [metaGenre, setMetaGenreRaw] = useState(project.metaGenre || "");
  const [metaYear, setMetaYearRaw] = useState(project.metaYear || "");
  const [metaDescription, setMetaDescriptionRaw] = useState(project.metaDescription || "");
  const [engineOptions, setEngineOptionsRaw] = useState<Record<string, any>>(project.engineOptions || {});
  const [isExporting, setIsExporting] = useState(false);
  const [inspectedSpeaker, setInspectedSpeaker] = useState<string | null>(null);
  const [resegmentModel, setResegmentModelRaw] = useState(DEFAULT_MODEL.id);
  const [resegmentMerge, setResegmentMerge] = useState(true);
  const [isMergingChunks, setIsMergingChunks] = useState(false);

  // Dirty-tracking wrappers
  const mark = () => setIsDirty(true);
  const setTtsEngine = (v: string) => { setTtsEngineRaw(v); mark(); };
  const setNarratorVoice = (v: string) => { setNarratorVoiceRaw(v); mark(); };
  const setNarratorSpeed = (v: number) => { setNarratorSpeedRaw(v); mark(); };
  const setBaseVoiceId = (v: string) => { setBaseVoiceIdRaw(v); mark(); };
  const setExaggeration = (v: number) => { setExaggerationRaw(v); mark(); };
  const setPauseDuration = (v: number) => { setPauseDurationRaw(v); mark(); };
  const setNarratorEmotion = (v: NarratorEmotion) => { setNarratorEmotionRaw(v); mark(); };
  const setDialogueEmotionMode = (v: DialogueEmotionMode) => { setDialogueEmotionModeRaw(v); mark(); };
  const setOutputFormat = (v: OutputFormat) => { setOutputFormatRaw(v); mark(); };
  const setMetaAuthor = (v: string) => { setMetaAuthorRaw(v); mark(); };
  const setMetaNarrator = (v: string) => { setMetaNarratorRaw(v); mark(); };
  const setMetaGenre = (v: string) => { setMetaGenreRaw(v); mark(); };
  const setMetaYear = (v: string) => { setMetaYearRaw(v); mark(); };
  const setMetaDescription = (v: string) => { setMetaDescriptionRaw(v); mark(); };
  const setEngineOptions = (updater: Record<string, any> | ((prev: Record<string, any>) => Record<string, any>)) => {
    setEngineOptionsRaw(updater as any);
    mark();
  };
  const setResegmentModel = (v: string) => { setResegmentModelRaw(v); };

  const allDetectedSpeakers = useMemo(() => {
    const speakers = new Set<string>();
    for (const ch of project.chapters || []) {
      for (const sec of ch.sections || []) {
        for (const chunk of sec.chunks || []) {
          const s = chunk.speakerOverride || chunk.speaker;
          if (s) speakers.add(s);
        }
      }
    }
    return Array.from(speakers).sort();
  }, [project]);

  const unassignedDialogueCount = useMemo(() => {
    let count = 0;
    for (const ch of project.chapters || []) {
      for (const sec of ch.sections || []) {
        for (const chunk of sec.chunks || []) {
          if (chunk.segmentType === "dialogue" && !(chunk.speakerOverride || chunk.speaker)) {
            count++;
          }
        }
      }
    }
    return count;
  }, [project]);

  const parsedSpeakerConfigs: Record<string, SpeakerConfig> = useMemo(() => {
    try {
      return project.speakersJson ? JSON.parse(project.speakersJson) : {};
    } catch {
      return {};
    }
  }, [project.speakersJson]);

  const [speakerConfigs, setSpeakerConfigsRaw] = useState<Record<string, SpeakerConfig>>({});
  const setSpeakerConfigs = (updater: Record<string, SpeakerConfig> | ((prev: Record<string, SpeakerConfig>) => Record<string, SpeakerConfig>)) => {
    setSpeakerConfigsRaw(updater as any);
    mark();
  };

  const initSpeakerConfigs = () => {
    const configs: Record<string, SpeakerConfig> = {};
    for (const name of allDetectedSpeakers) {
      configs[name] = parsedSpeakerConfigs[name] || {
        name,
        voiceSampleId: null,
        pitchOffset: 0,
        speedFactor: 1.0,
      };
    }
    return configs;
  };

  useEffect(() => {
    setTtsEngineRaw(project.ttsEngine || "edge-tts");
    setNarratorVoiceRaw(project.narratorVoiceId || "");
    setNarratorSpeedRaw(project.narratorSpeed ?? 1.0);
    setBaseVoiceIdRaw(project.baseVoiceId || "");
    setExaggerationRaw(project.exaggeration ?? 0.5);
    setPauseDurationRaw(project.pauseDuration ?? 150);
    setNarratorEmotionRaw(project.narratorEmotion || "auto");
    setDialogueEmotionModeRaw(project.dialogueEmotionMode || "per-chunk");
    setOutputFormatRaw(project.outputFormat || "mp3");
    setMetaAuthorRaw(project.metaAuthor || "");
    setMetaNarratorRaw(project.metaNarrator || "");
    setMetaGenreRaw(project.metaGenre || "");
    setMetaYearRaw(project.metaYear || "");
    setMetaDescriptionRaw(project.metaDescription || "");
    setEngineOptionsRaw(project.engineOptions || {});
    setSpeakerConfigsRaw(initSpeakerConfigs());
    setResegmentModelRaw(DEFAULT_MODEL.id);
    setIsDirty(false);
  }, [project.id]);

  useEffect(() => {
    setSpeakerConfigsRaw(initSpeakerConfigs());
  }, [allDetectedSpeakers.join(","), project.speakersJson]);

  useEffect(() => {
    if (!baseVoiceId) {
      const engine = registeredEngines.find((e: any) => (e.engine_id || e.id) === ttsEngine);
      const firstBase = engine?.base_voices?.[0]?.id;
      if (firstBase) setBaseVoiceIdRaw(firstBase);
    }
  }, [ttsEngine, registeredEngines, baseVoiceId]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      await apiRequest("PATCH", `/api/projects/${project.id}`, {
        ttsEngine,
        narratorVoiceId: narratorVoice || null,
        narratorSpeed,
        baseVoiceId: baseVoiceId || null,
        exaggeration,
        pauseDuration,
        narratorEmotion,
        dialogueEmotionMode,
        outputFormat,
        metaAuthor: metaAuthor || null,
        metaNarrator: metaNarrator || null,
        metaGenre: metaGenre || null,
        metaYear: metaYear || null,
        metaDescription: metaDescription || null,
        speakersJson: JSON.stringify(speakerConfigs),
        engineOptions: Object.keys(engineOptions).length > 0 ? engineOptions : null,
      });
    },
    onSuccess: () => {
      toast({ title: "Settings saved" });
      setIsDirty(false);
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Failed to save", description: error.message, variant: "destructive" });
    },
  });

  const coverUploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/projects/${project.id}/cover`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    onSuccess: () => {
      toast({ title: "Cover image uploaded" });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Upload failed", description: error.message, variant: "destructive" });
    },
  });

  const coverDeleteMutation = useMutation({
    mutationFn: async () => {
      await apiRequest("DELETE", `/api/projects/${project.id}/cover`);
    },
    onSuccess: () => {
      toast({ title: "Cover image removed" });
      onRefresh();
    },
  });

  const handleExport = async () => {
    setIsExporting(true);
    toast({ title: "Starting export...", description: "Saving settings and queuing export job." });
    try {
      await apiRequest("PATCH", `/api/projects/${project.id}`, {
        ttsEngine,
        narratorVoiceId: narratorVoice || null,
        narratorSpeed,
        baseVoiceId: baseVoiceId || null,
        exaggeration,
        pauseDuration,
        narratorEmotion,
        dialogueEmotionMode,
        outputFormat,
        metaAuthor: metaAuthor || null,
        metaNarrator: metaNarrator || null,
        metaGenre: metaGenre || null,
        metaYear: metaYear || null,
        metaDescription: metaDescription || null,
        speakersJson: JSON.stringify(speakerConfigs),
        engineOptions: Object.keys(engineOptions).length > 0 ? engineOptions : null,
      });
      setIsDirty(false);

      await apiRequest("POST", `/api/projects/${project.id}/export`, { format: outputFormat });
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
      toast({ title: "Export job started", description: "Check the Jobs tab for progress and download." });
    } catch (error: any) {
      toast({ title: "Export failed", description: error.message, variant: "destructive" });
    } finally {
      setIsExporting(false);
    }
  };

  const handleDownloadCueSheet = () => {
    const sortedChapters = [...chapters].sort((a, b) => a.chapterIndex - b.chapterIndex);
    const audioFiles = project.audioFiles || [];

    const chapterAudioMap = new Map<string, number>();
    for (const af of audioFiles) {
      if (af.scopeType === "chapter" && af.durationSeconds != null) {
        chapterAudioMap.set(af.scopeId, af.durationSeconds);
      }
    }

    const sectionAudioMap = new Map<string, number>();
    for (const af of audioFiles) {
      if (af.scopeType === "section" && af.durationSeconds != null) {
        sectionAudioMap.set(af.scopeId, af.durationSeconds);
      }
    }

    const formatCueTime = (totalSeconds: number): string => {
      const totalFrames = Math.floor(totalSeconds * 75);
      const frames = totalFrames % 75;
      const totalSecs = Math.floor(totalFrames / 75);
      const minutes = Math.floor(totalSecs / 60);
      const secs = totalSecs % 60;
      return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}:${String(frames).padStart(2, "0")}`;
    };

    const safeTitle = (project.title || "audiobook").replace(/[^\w\s-]/g, "").trim();
    const mp3Filename = `${safeTitle}.mp3`;

    let cue = `FILE "${mp3Filename}" MP3\n`;
    let cumulativeSeconds = 0;

    for (let i = 0; i < sortedChapters.length; i++) {
      const ch = sortedChapters[i];
      const trackNum = i + 1;
      const title = ch.title || `Chapter ${trackNum}`;

      cue += `TRACK ${String(trackNum).padStart(2, "0")} AUDIO\n`;
      cue += `  TITLE "${title.replace(/"/g, '\\"')}"\n`;
      cue += `  INDEX 01 ${formatCueTime(cumulativeSeconds)}\n`;

      let chapterDuration = chapterAudioMap.get(ch.id);
      if (chapterDuration == null) {
        chapterDuration = 0;
        for (const sec of ch.sections || []) {
          const secDur = sectionAudioMap.get(sec.id);
          if (secDur != null) {
            chapterDuration += secDur;
          }
        }
      }
      cumulativeSeconds += chapterDuration;
    }

    const blob = new Blob([cue], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safeTitle}.cue`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: "Cue sheet downloaded" });
  };

  // Expose save/isDirty via ref
  useImperativeHandle(ref, () => ({
    save: () => {
      saveMutation.mutate();
    },
    isDirty: () => isDirty,
  }), [isDirty, saveMutation]);

  const chapters = project.chapters || [];
  const totalChunks = chapters.reduce(
    (sum, ch) => sum + (ch.sections || []).reduce((s, sec) => s + (sec.chunks?.length || 0), 0),
    0
  );

  // Compute audio files for output-files view
  const projectAudioFiles = useMemo(() => {
    const allAudio = project.audioFiles || [];
    const exportFiles = allAudio.filter(af => af.scopeType === "export");
    const chapterIds = chapters.map(c => c.id);
    let chapterFiles = allAudio.filter(af => af.scopeType === "chapter" && chapterIds.includes(af.scopeId));
    const chapterOrder = new Map(chapterIds.map((id, idx) => [id, idx]));
    if (chapterFiles.length === 0) {
      const sectionSortKey = new Map<string, number>();
      let sectionOrder = 0;
      const sectionIdToChapterIdx = new Map<string, number>();
      for (const ch of chapters) {
        const chIdx = chapterOrder.get(ch.id) ?? 0;
        for (const sec of (ch.sections || [])) {
          sectionIdToChapterIdx.set(sec.id, chIdx);
          sectionSortKey.set(sec.id, sectionOrder++);
        }
      }
      chapterFiles = allAudio.filter(af => af.scopeType === "section" && sectionIdToChapterIdx.has(af.scopeId));
      chapterFiles.sort((a, b) => (sectionSortKey.get(a.scopeId) ?? 0) - (sectionSortKey.get(b.scopeId) ?? 0));
    } else {
      chapterFiles.sort((a, b) => (chapterOrder.get(a.scopeId) ?? 0) - (chapterOrder.get(b.scopeId) ?? 0));
    }
    return [...exportFiles, ...chapterFiles];
  }, [project.audioFiles, chapters]);

  // ── View: "project" ──────────────────────────────────────────────────────

  if (view === "project") {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Book className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-bold" data-testid="text-detail-title">{project.title}</h2>
          <Badge variant="outline">{project.status}</Badge>
        </div>

        <div className="flex gap-4 text-sm text-muted-foreground">
          <span>{chapters.length} chapters</span>
          <span>{totalChunks} chunks</span>
          <span>{project.sourceType}</span>
        </div>

        {project.status === "segmenting" && (() => {
          const total = chapters.length;
          const completed = chapters.filter(c => c.status === "segmented" || c.status === "failed").length;
          const segmentingChapter = chapters.find(c => c.status === "segmenting");
          const totalSections = segmentingChapter?.sections?.length ?? 0;
          const completedSections = segmentingChapter?.sections?.filter(
            (s: any) => s.status === "segmented" || s.status === "failed"
          ).length ?? 0;
          const pct = total > 0
            ? Math.round(((completed + (totalSections > 0 ? completedSections / totalSections : 0)) / total) * 100)
            : 0;
          return (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Segmenting… {completed}/{total} chapters ({pct}%)
                  {segmentingChapter && totalSections > 0 && (
                    <span className="ml-1">— section {completedSections}/{totalSections} in current chapter</span>
                  )}
                </span>
              </div>
              <Progress value={pct} className="h-1.5" />
            </div>
          );
        })()}

        <Separator />

        <div className="space-y-1">
          <h3 className="text-sm font-semibold">Output Format</h3>
          <p className="text-xs text-muted-foreground">Choose how the final audiobook will be exported</p>
        </div>

        <div className="grid gap-4">
          <Select value={outputFormat} onValueChange={(v) => setOutputFormat(v as OutputFormat)}>
            <SelectTrigger data-testid="select-output-format">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="mp3">Single MP3 file</SelectItem>
              <SelectItem value="mp3-chapters">MP3 per chapter (ZIP)</SelectItem>
              <SelectItem value="m4b">M4B Audiobook (with chapters)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <Separator />

        <div className="space-y-1">
          <h3 className="text-sm font-semibold">Audiobook Metadata</h3>
          <p className="text-xs text-muted-foreground">Embedded in the exported file as ID3/MP4 tags</p>
        </div>

        <div className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Author</Label>
              <Input
                value={metaAuthor}
                onChange={(e) => setMetaAuthor(e.target.value)}
                placeholder="Author name"
                data-testid="input-meta-author"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Narrator</Label>
              <Input
                value={metaNarrator}
                onChange={(e) => setMetaNarrator(e.target.value)}
                placeholder="Narrator name"
                data-testid="input-meta-narrator"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Genre</Label>
              <Input
                value={metaGenre}
                onChange={(e) => setMetaGenre(e.target.value)}
                placeholder="e.g. Fiction, Sci-Fi"
                data-testid="input-meta-genre"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Year</Label>
              <Input
                value={metaYear}
                onChange={(e) => setMetaYear(e.target.value)}
                placeholder="e.g. 2025"
                data-testid="input-meta-year"
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label className="text-xs">Description</Label>
            <Textarea
              value={metaDescription}
              onChange={(e) => setMetaDescription(e.target.value)}
              placeholder="Brief description of the audiobook..."
              rows={3}
              data-testid="input-meta-description"
            />
          </div>

          <div className="space-y-2">
            <Label className="text-xs">Cover Image</Label>
            <div className="flex items-center gap-3">
              {project.hasCoverImage ? (
                <div className="relative">
                  <img
                    src={`/api/projects/${project.id}/cover`}
                    alt="Cover"
                    className="w-16 h-16 rounded object-cover border"
                    data-testid="img-cover-preview"
                  />
                  <button
                    onClick={() => coverDeleteMutation.mutate()}
                    className="absolute -top-1 -right-1 bg-destructive text-destructive-foreground rounded-full w-4 h-4 flex items-center justify-center text-xs"
                    data-testid="button-remove-cover"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <div className="w-16 h-16 rounded border border-dashed flex items-center justify-center text-muted-foreground">
                  <Image className="h-6 w-6" />
                </div>
              )}
              <div>
                <input
                  ref={coverInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) coverUploadMutation.mutate(file);
                  }}
                  data-testid="input-cover-file"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => coverInputRef.current?.click()}
                  disabled={coverUploadMutation.isPending}
                  data-testid="button-upload-cover"
                >
                  <Upload className="h-3.5 w-3.5 mr-1" />
                  {coverUploadMutation.isPending ? "Uploading..." : "Upload Cover"}
                </Button>
              </div>
            </div>
          </div>
        </div>

        <Separator />

        <div className="space-y-3">
          <h3 className="text-sm font-semibold">Re-segment Project</h3>
          <p className="text-xs text-muted-foreground">
            Re-analyze the text with a different LLM model. This will replace all existing chapters, sections, and chunks.
          </p>
          <div className="flex items-end gap-2">
            <div className="flex-1 space-y-1">
              <Label className="text-xs">Analysis Model</Label>
              <Select value={resegmentModel} onValueChange={setResegmentModel}>
                <SelectTrigger data-testid="select-resegment-model" className="h-9">
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
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  const res = await fetch(`/api/projects/${project.id}/segment`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ model: resegmentModel, merge_short_chunks: resegmentMerge }),
                    credentials: "include",
                  });
                  if (!res.ok) throw new Error(await res.text());
                  toast({ title: "Re-segmentation started", description: "Running in the background." });
                  queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id] });
                  onRefresh();
                } catch (err: any) {
                  toast({ title: "Re-segmentation failed", description: err.message, variant: "destructive" });
                }
              }}
              disabled={project.status === "segmenting"}
              data-testid="button-resegment"
            >
              <RefreshCw className="h-3.5 w-3.5 mr-1" />
              {project.status === "segmenting" ? "Segmenting..." : "Re-segment"}
            </Button>
          </div>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <Checkbox
              checked={resegmentMerge}
              onCheckedChange={(v) => setResegmentMerge(!!v)}
            />
            Merge short / punctuation-only chunks after segmentation
          </label>
        </div>

        <Separator />

        <div className="space-y-3">
          <h3 className="text-sm font-semibold">Merge Short Chunks</h3>
          <p className="text-xs text-muted-foreground">
            Run the chunk-merging pass on the current segmentation without re-analyzing. Joins punctuation-only and short (≤3 word) chunks with same-speaker neighbours.
          </p>
          <Button
            variant="outline"
            size="sm"
            disabled={isMergingChunks || project.status === "segmenting"}
            onClick={async () => {
              setIsMergingChunks(true);
              try {
                const res = await fetch(`/api/projects/${project.id}/merge-short-chunks`, {
                  method: "POST",
                  credentials: "include",
                });
                if (!res.ok) throw new Error(await res.text());
                const data = await res.json();
                toast({
                  title: "Merge complete",
                  description: data.eliminated > 0
                    ? `Merged away ${data.eliminated} chunk(s).`
                    : "No chunks needed merging.",
                });
                queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id] });
                onRefresh();
              } catch (err: any) {
                toast({ title: "Merge failed", description: err.message, variant: "destructive" });
              } finally {
                setIsMergingChunks(false);
              }
            }}
          >
            {isMergingChunks
              ? <><Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />Merging…</>
              : <><Merge className="h-3.5 w-3.5 mr-1" />Merge Short Chunks</>}
          </Button>
        </div>
      </div>
    );
  }

  // ── View: "engine-settings" ──────────────────────────────────────────────

  if (view === "engine-settings") {
    const currentEngine = registeredEngines.find((e: any) => (e.engine_id || e.id) === ttsEngine);
    const baseVoices = currentEngine?.base_voices || [];
    const params: any[] = currentEngine?.engine_params || [];

    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-bold" data-testid="text-detail-title">Engine Settings</h2>
        </div>

        <div className="grid gap-4">
          <div className="space-y-2">
            <Label>TTS Engine</Label>
            <Select value={ttsEngine} onValueChange={(v) => {
              setTtsEngine(v);
              const newEngine = registeredEngines.find((e: any) => (e.engine_id || e.id) === v);
              const firstBase = newEngine?.base_voices?.[0]?.id || "";
              setBaseVoiceIdRaw(firstBase);
              const defaults: Record<string, any> = {};
              for (const p of (newEngine?.engine_params || [])) {
                defaults[p.short_name] = p.default_value;
              }
              setEngineOptionsRaw(defaults);
              mark();
            }}>
              <SelectTrigger data-testid="select-tts-engine">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {allEngines.map((e) => (
                  <SelectItem key={e.id} value={e.id}>{e.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Pause Between Chunks: {pauseDuration}ms</Label>
            <Slider
              value={[pauseDuration]}
              onValueChange={([v]) => setPauseDuration(v)}
              min={0}
              max={3000}
              step={50}
              data-testid="slider-pause"
            />
          </div>

          {baseVoices.length > 0 && (
            <div className="space-y-2">
              <Label>Base Voice / Language</Label>
              <p className="text-xs text-muted-foreground">Controls the language and accent of generated speech</p>
              <Select value={baseVoiceId} onValueChange={setBaseVoiceId}>
                <SelectTrigger data-testid="select-base-voice">
                  <SelectValue placeholder="Select base voice..." />
                </SelectTrigger>
                <SelectContent>
                  {baseVoices.map((v: any) => (
                    <SelectItem key={v.id} value={v.id}>
                      {v.display_name}
                      {v.extra_info && ` — ${v.extra_info}`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {params.length > 0 && (
            <div className="space-y-3">
              <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Model Options</Label>
              {params.map((p: any) => (
                <div key={p.short_name} className="space-y-1">
                  <Label>{p.friendly_name}</Label>
                  {p.data_type === "list" ? (
                    <Select
                      value={String(engineOptions[p.short_name] ?? p.default_value)}
                      onValueChange={(v) => setEngineOptions((prev) => ({ ...prev, [p.short_name]: v }))}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(p.list_options || []).map((opt: string) => (
                          <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      type="number"
                      min={p.min_value}
                      max={p.max_value}
                      step={p.data_type === "float" ? 0.05 : 1}
                      value={engineOptions[p.short_name] ?? p.default_value}
                      onChange={(e) => setEngineOptions((prev) => ({ ...prev, [p.short_name]: Number(e.target.value) }))}
                    />
                  )}
                </div>
              ))}
            </div>
          )}

          {project.hasSourceFile && (
            <div className="space-y-2">
              <Separator />
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const a = document.createElement("a");
                  a.href = `/api/projects/${project.id}/source-file`;
                  a.click();
                }}
                data-testid="button-download-source"
              >
                <Download className="h-4 w-4 mr-2" />
                Download Source File
              </Button>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── View: "voice-settings" ───────────────────────────────────────────────

  if (view === "voice-settings") {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-bold" data-testid="text-detail-title">Voice Settings</h2>
        </div>

        <div className="grid gap-4">
          <div className="space-y-2">
            <Label>Narrator Voice</Label>
            <Select value={narratorVoice} onValueChange={setNarratorVoice}>
              <SelectTrigger data-testid="select-narrator-voice">
                <SelectValue placeholder="Select a voice..." />
              </SelectTrigger>
              <SelectContent>
                <VoiceSelectOptions opts={allVoices.map(v => ({ value: v.id, label: v.label }))} favoriteIds={favoriteIds} />
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Narrator Speed</Label>
              <span className="text-xs font-mono text-muted-foreground" data-testid="text-narrator-speed">
                {narratorSpeed.toFixed(2)}x
              </span>
            </div>
            <Slider
              value={[narratorSpeed]}
              min={0.7}
              max={1.3}
              step={0.05}
              onValueChange={([v]) => setNarratorSpeed(v)}
              data-testid="slider-narrator-speed"
            />
          </div>

          <div className="space-y-2">
            <Label>Exaggeration: {exaggeration.toFixed(2)}</Label>
            <Slider
              value={[exaggeration]}
              onValueChange={([v]) => setExaggeration(v)}
              min={0}
              max={1}
              step={0.05}
              data-testid="slider-exaggeration"
            />
          </div>

          <div className="space-y-2">
            <Label>Narrator Emotion</Label>
            <p className="text-xs text-muted-foreground">Override detected emotions for narration segments</p>
            <Select value={narratorEmotion} onValueChange={(v) => setNarratorEmotion(v as NarratorEmotion)}>
              <SelectTrigger data-testid="select-narrator-emotion">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto-detect</SelectItem>
                {CANONICAL_EMOTIONS.map((e) => (
                  <SelectItem key={e} value={e}>{e.charAt(0).toUpperCase() + e.slice(1)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Dialogue Emotion Mode</Label>
            <p className="text-xs text-muted-foreground">How to handle emotions when a quote spans multiple chunks</p>
            <Select value={dialogueEmotionMode} onValueChange={(v) => setDialogueEmotionMode(v as DialogueEmotionMode)}>
              <SelectTrigger data-testid="select-dialogue-emotion-mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="per-chunk">Per chunk (default)</SelectItem>
                <SelectItem value="first-chunk">Use first chunk's emotion</SelectItem>
                <SelectItem value="word-count-majority">Dominant emotion (by word count)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
    );
  }

  // ── View: "characters" ───────────────────────────────────────────────────

  if (view === "characters") {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-bold" data-testid="text-detail-title">Characters</h2>
        </div>

        {allDetectedSpeakers.length === 0 && unassignedDialogueCount === 0 ? (
          <p className="text-sm text-muted-foreground">No speakers detected in this project yet.</p>
        ) : (
          <>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold flex items-center gap-1.5">
                <Users className="h-4 w-4" />
                Speaker Voices
              </h3>
              <p className="text-xs text-muted-foreground">
                Assign voices to detected speakers. Click a name to inspect their quotes.
              </p>
            </div>

            {unassignedDialogueCount > 0 && (
              <button
                type="button"
                onClick={() => setInspectedSpeaker("__unassigned__")}
                className="w-full flex items-center gap-2 rounded-lg border border-yellow-300 dark:border-yellow-700 bg-yellow-50 dark:bg-yellow-950/20 p-3 text-sm text-yellow-800 dark:text-yellow-200 hover:bg-yellow-100 dark:hover:bg-yellow-950/30 transition-colors cursor-pointer"
                data-testid="button-unassigned-dialogue"
              >
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>
                  {unassignedDialogueCount} dialogue chunk{unassignedDialogueCount !== 1 ? "s" : ""} without a speaker — click to assign
                </span>
              </button>
            )}

            <div className="space-y-3">
              {allDetectedSpeakers.map((name) => {
                const config = speakerConfigs[name] || { name, voiceSampleId: null, pitchOffset: 0, speedFactor: 1.0 };
                return (
                  <div key={name} className="rounded-lg border p-3 space-y-2" data-testid={`speaker-config-${name}`}>
                    <button
                      type="button"
                      onClick={() => setInspectedSpeaker(name)}
                      className="text-sm font-medium text-primary hover:underline cursor-pointer"
                      data-testid={`button-inspect-speaker-${name}`}
                    >
                      {name}
                    </button>

                    <div className="space-y-1">
                      <Label className="text-xs">Voice</Label>
                      <Select
                        value={config.voiceSampleId || "__narrator__"}
                        onValueChange={(v) =>
                          setSpeakerConfigs((prev) => ({
                            ...prev,
                            [name]: { ...config, voiceSampleId: v === "__narrator__" ? null : v },
                          }))
                        }
                      >
                        <SelectTrigger data-testid={`select-speaker-voice-${name}`}>
                          <SelectValue placeholder="Use narrator default" />
                        </SelectTrigger>
                        <SelectContent>
                          <VoiceSelectOptions
                            opts={allVoices.map(v => ({ value: v.id, label: v.label }))}
                            favoriteIds={favoriteIds}
                            prepend={<SelectItem value="__narrator__">Use narrator default</SelectItem>}
                          />
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <Label className="text-xs">Speed</Label>
                        <span className="text-xs font-mono text-muted-foreground" data-testid={`text-speed-${name}`}>
                          {(config.speedFactor ?? 1.0).toFixed(2)}x
                        </span>
                      </div>
                      <Slider
                        value={[config.speedFactor ?? 1.0]}
                        min={0.7}
                        max={1.3}
                        step={0.05}
                        onValueChange={([v]) =>
                          setSpeakerConfigs((prev) => ({
                            ...prev,
                            [name]: { ...config, speedFactor: v },
                          }))
                        }
                        data-testid={`slider-speed-${name}`}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            <SpeakerInspectorDialog
              open={!!inspectedSpeaker}
              onOpenChange={(open) => { if (!open) setInspectedSpeaker(null); }}
              speakerName={inspectedSpeaker || ""}
              project={project}
              allSpeakers={allDetectedSpeakers}
              onMergeComplete={onRefresh}
            />
          </>
        )}
      </div>
    );
  }

  // ── View: "output-files" ─────────────────────────────────────────────────

  if (view === "output-files") {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Music className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-bold" data-testid="text-detail-title">Generated Audio Files</h2>
        </div>

        <div className="flex flex-wrap gap-2">
          {outputFormat === "mp3" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadCueSheet}
              data-testid="button-download-cue"
            >
              <FileText className="h-4 w-4 mr-2" />
              Download Cue Sheet
            </Button>
          )}
        </div>

        <ProjectAudioList audioFiles={projectAudioFiles} projectId={project.id} onDelete={onRefresh} />
      </div>
    );
  }

  return null;
});

// ─── Chapter Detail Panel ────────────────────────────────────────────────────

function ChapterDetailPanel({
  chapter,
  project,
  allEngines,
  allVoices,
  favoriteIds,
  onRefresh,
}: {
  chapter: ProjectChapter;
  project: ProjectData;
  allEngines: { id: string; label: string }[];
  allVoices: { id: string; label: string }[];
  favoriteIds: Set<string>;
  onRefresh: () => void;
}) {
  const { toast } = useToast();
  const [ttsEngine, setTtsEngine] = useState(chapter.ttsEngine || "");
  const [narratorVoice, setNarratorVoice] = useState(chapter.narratorVoiceId || "");

  useEffect(() => {
    setTtsEngine(chapter.ttsEngine || "");
    setNarratorVoice(chapter.narratorVoiceId || "");
  }, [chapter.id]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      await apiRequest("PATCH", `/api/projects/${project.id}/chapters/${chapter.id}`, {
        ttsEngine: ttsEngine && ttsEngine !== "__default__" ? ttsEngine : null,
        narratorVoiceId: narratorVoice && narratorVoice !== "__default__" ? narratorVoice : null,
      });
    },
    onSuccess: () => {
      toast({ title: "Chapter settings saved" });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Failed to save", description: error.message, variant: "destructive" });
    },
  });

  const sections = chapter.sections || [];
  const chunkCount = sections.reduce((sum, s) => sum + (s.chunks?.length || 0), 0);
  const speakers = new Set<string>();
  sections.forEach((sec) =>
    (sec.chunks || []).forEach((chunk) => {
      if (chunk.speaker) speakers.add(chunk.speaker);
    })
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Layers className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-bold" data-testid="text-detail-title">
          {chapter.title || `Chapter ${chapter.chapterIndex + 1}`}
        </h2>
        <Badge variant="outline">{chapter.status}</Badge>
      </div>

      <div className="flex gap-4 text-sm text-muted-foreground">
        <span>{sections.length} sections</span>
        <span>{chunkCount} chunks</span>
      </div>

      {speakers.size > 0 && (
        <div className="space-y-1">
          <Label className="text-xs">Detected Speakers</Label>
          <div className="flex flex-wrap gap-1">
            {Array.from(speakers).map((s) => (
              <Badge key={s} variant="secondary" className="text-xs">{s}</Badge>
            ))}
          </div>
        </div>
      )}

      <Separator />

      <div className="grid gap-4">
        <div className="space-y-2">
          <Label>TTS Engine Override</Label>
          <Select value={ttsEngine} onValueChange={setTtsEngine}>
            <SelectTrigger data-testid="select-chapter-engine">
              <SelectValue placeholder="Use book default" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__default__">Use book default</SelectItem>
              {allEngines.map((e) => (
                <SelectItem key={e.id} value={e.id}>{e.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Narrator Voice Override</Label>
          <Select value={narratorVoice} onValueChange={setNarratorVoice}>
            <SelectTrigger data-testid="select-chapter-voice">
              <SelectValue placeholder="Use book default" />
            </SelectTrigger>
            <SelectContent>
              <VoiceSelectOptions
                opts={allVoices.map(v => ({ value: v.id, label: v.label }))}
                favoriteIds={favoriteIds}
                prepend={<SelectItem value="__default__">Use book default</SelectItem>}
              />
            </SelectContent>
          </Select>
        </div>

        <Button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          size="sm"
          data-testid="button-save-chapter"
        >
          <Save className="h-4 w-4 mr-2" />
          {saveMutation.isPending ? "Saving..." : "Save Overrides"}
        </Button>
      </div>
    </div>
  );
}

// ─── Section Detail Panel ────────────────────────────────────────────────────

function SectionDetailPanel({ section, project, onRefresh }: { section: ProjectSection; project: ProjectData; onRefresh: () => void }) {
  const { toast } = useToast();
  const [rechunkModel, setRechunkModel] = useState(DEFAULT_MODEL.id);
  const chunks = section.chunks || [];
  const totalWords = chunks.reduce((sum, c) => sum + (c.wordCount || 0), 0);

  const rechunkMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/projects/${project.id}/sections/${section.id}/rechunk`, {
        model: rechunkModel,
      });
      return res.json();
    },
    onSuccess: (data) => {
      toast({ title: "Re-chunk complete", description: `Created ${data.chunksCreated} chunks` });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Re-chunk failed", description: error.message, variant: "destructive" });
      onRefresh();
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FileText className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-bold" data-testid="text-detail-title">
          Section {section.sectionIndex + 1}
        </h2>
        <Badge variant="outline">{section.status}</Badge>
      </div>
      {section.title && (
        <p className="text-sm text-muted-foreground">{section.title}</p>
      )}
      <div className="flex gap-4 text-sm text-muted-foreground">
        <span>{chunks.length} chunks</span>
        <span>{totalWords} words</span>
      </div>
      {section.errorMessage && (
        <div className="text-sm text-red-500 bg-red-50 dark:bg-red-950/30 p-2 rounded">
          {section.errorMessage}
        </div>
      )}

      {section.hasRawText && (section.status === "segmented" || section.status === "failed") && (
        <div className="space-y-2 pt-2">
          <h3 className="text-sm font-semibold">Re-chunk Section</h3>
          <p className="text-xs text-muted-foreground">
            Re-analyze this section with the LLM to regenerate chunks and speaker assignments. Existing chunks will be replaced.
          </p>
          <div className="flex items-center gap-2">
            <Select value={rechunkModel} onValueChange={setRechunkModel}>
              <SelectTrigger data-testid="select-rechunk-model" className="h-9 flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LLM_MODELS.map((m) => (
                  <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              size="sm"
              variant="outline"
              onClick={() => rechunkMutation.mutate()}
              disabled={rechunkMutation.isPending}
              data-testid="button-rechunk-section"
            >
              {rechunkMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5 mr-1" />
              )}
              {rechunkMutation.isPending ? "Re-chunking..." : "Re-chunk"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Chunk Detail Panel ──────────────────────────────────────────────────────

function ChunkDetailPanel({
  chunk,
  project,
  onRefresh,
}: {
  chunk: ProjectChunk;
  project: ProjectData;
  onRefresh: () => void;
}) {
  const { toast } = useToast();
  const [speakerOverride, setSpeakerOverride] = useState(chunk.speakerOverride || "");
  const [emotionOverride, setEmotionOverride] = useState(chunk.emotionOverride || "");

  useEffect(() => {
    setSpeakerOverride(chunk.speakerOverride || "");
    setEmotionOverride(chunk.emotionOverride || "");
  }, [chunk.id]);

  const allSpeakers = new Set<string>();
  (project.chapters || []).forEach((ch) =>
    (ch.sections || []).forEach((sec) =>
      (sec.chunks || []).forEach((c) => {
        if (c.speaker) allSpeakers.add(c.speaker);
      })
    )
  );

  const saveMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, any> = {
        emotionOverride: emotionOverride && emotionOverride !== "__auto__" ? emotionOverride : null,
      };
      if (speakerOverride === "__narrator__") {
        body.speakerOverride = null;
        body.segmentType = "narration";
      } else if (speakerOverride && speakerOverride !== "__auto__") {
        body.speakerOverride = speakerOverride;
        body.segmentType = "dialogue";
      } else {
        body.speakerOverride = null;
      }
      await apiRequest("PATCH", `/api/projects/${project.id}/chunks/${chunk.id}`, body);
    },
    onSuccess: () => {
      toast({ title: "Chunk overrides saved" });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Failed to save", description: error.message, variant: "destructive" });
    },
  });

  const combineMutation = useMutation({
    mutationFn: async () => {
      await apiRequest("POST", `/api/projects/${project.id}/chunks/${chunk.id}/combine-with-previous`);
    },
    onSuccess: () => {
      toast({ title: "Chunks combined successfully" });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Failed to combine", description: error.message, variant: "destructive" });
    },
  });

  const isFirstChunk = chunk.chunkIndex === 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Type className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-bold" data-testid="text-detail-title">Chunk</h2>
        <Badge variant="outline">{chunk.segmentType}</Badge>
      </div>

      <div className="p-3 rounded-lg bg-muted/50 text-sm leading-relaxed" data-testid="text-chunk-content">
        {chunk.text}
      </div>

      <div className="flex gap-4 text-xs text-muted-foreground">
        <span>{chunk.wordCount} words</span>
        <span>~{chunk.approxDurationSeconds?.toFixed(1)}s</span>
        {chunk.speaker && <span>Speaker: {chunk.speaker}</span>}
        {chunk.emotion && (
          <Badge variant="secondary" className="text-xs">{chunk.emotion}</Badge>
        )}
      </div>

      <Separator />

      <div className="grid gap-4">
        <div className="space-y-2">
          <Label>
            Speaker Override
            {chunk.speaker && (
              <span className="text-xs text-muted-foreground ml-2">(auto: {chunk.speaker})</span>
            )}
          </Label>
          <Select value={speakerOverride} onValueChange={setSpeakerOverride}>
            <SelectTrigger data-testid="select-chunk-speaker">
              <SelectValue placeholder="Use auto-detected" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__auto__">Use auto-detected</SelectItem>
              <SelectItem value="__narrator__">Narrator (narration)</SelectItem>
              {Array.from(allSpeakers).map((s) => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>
            Emotion Override
            {chunk.emotion && (
              <span className="text-xs text-muted-foreground ml-2">(auto: {chunk.emotion})</span>
            )}
          </Label>
          <Select value={emotionOverride} onValueChange={setEmotionOverride}>
            <SelectTrigger data-testid="select-chunk-emotion">
              <SelectValue placeholder="Use auto-detected" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__auto__">Use auto-detected</SelectItem>
              {CANONICAL_EMOTIONS.map((e) => (
                <SelectItem key={e} value={e}>{e}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          size="sm"
          data-testid="button-save-chunk"
        >
          <Save className="h-4 w-4 mr-2" />
          {saveMutation.isPending ? "Saving..." : "Save Overrides"}
        </Button>

        {!isFirstChunk && (
          <Button
            onClick={() => combineMutation.mutate()}
            disabled={combineMutation.isPending}
            size="sm"
            variant="outline"
            data-testid="button-combine-chunk"
          >
            <Merge className="h-4 w-4 mr-2" />
            {combineMutation.isPending ? "Combining..." : "Combine with Previous Chunk"}
          </Button>
        )}
      </div>
    </div>
  );
}
