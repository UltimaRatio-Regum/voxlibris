import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Wand2, Save, Book, Layers, FileText, Type } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import { ProjectAudioList } from "@/components/ProjectAudioList";
import { TTS_ENGINES } from "@/lib/tts-engines";
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
} from "@shared/schema";

const CANONICAL_EMOTIONS = [
  "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
  "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
];

interface ProjectDetailPanelProps {
  selection: TreeSelection;
  project: ProjectData;
  onRefresh: () => void;
}

export function ProjectDetailPanel({ selection, project, onRefresh }: ProjectDetailPanelProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: voiceSamples = [] } = useQuery<VoiceSample[]>({
    queryKey: ["/api/voices"],
  });

  const { data: libraryVoices = [] } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library"],
  });

  const { data: registeredEngines = [] } = useQuery<any[]>({
    queryKey: ["/api/tts-engines"],
  });

  const allEngines = [
    ...TTS_ENGINES.map((e) => ({ id: e.id, label: e.label })),
    ...registeredEngines.map((e: any) => ({ id: e.engine_id || e.id, label: e.engine_name || e.name || e.engine_id || e.id })),
  ];

  const allVoices = [
    ...voiceSamples.map((v) => ({ id: v.id, label: v.name })),
    ...libraryVoices.map((v) => ({ id: v.id, label: v.name })),
  ];

  const audioFiles = (project.audioFiles || []).filter((af) => {
    if (af.scopeType === selection.type && af.scopeId === selection.id) return true;
    if (selection.type === "project") return true;
    if (selection.type === "chunk" && af.scopeType === "chunk" && af.scopeId === selection.id) return true;
    if (selection.type === "section") {
      const section = selection.data as ProjectSection;
      const chunkIds = (section.chunks || []).map(c => c.id);
      return af.scopeType === "chunk" && chunkIds.includes(af.scopeId);
    }
    if (selection.type === "chapter") {
      const chapter = selection.data as ProjectChapter;
      const chunkIds = (chapter.sections || []).flatMap(s => (s.chunks || []).map(c => c.id));
      return af.scopeType === "chunk" && chunkIds.includes(af.scopeId);
    }
    return false;
  });

  const generateMutation = useMutation({
    mutationFn: async () => {
      const scopeId = selection.type === "project" ? project.id : selection.id;
      const res = await apiRequest("POST", `/api/projects/${project.id}/generate`, {
        scopeType: selection.type,
        scopeId,
      });
      return res.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Generation started",
        description: `Job created with ${data.totalSegments} segments. Check the Jobs tab for progress.`,
      });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Generation failed", description: error.message, variant: "destructive" });
    },
  });

  return (
    <div className="space-y-6" data-testid="project-detail-panel">
      {selection.type === "project" && (
        <ProjectSettingsPanel
          project={project}
          allEngines={allEngines}
          allVoices={allVoices}
          onRefresh={onRefresh}
        />
      )}

      {selection.type === "chapter" && (
        <ChapterDetailPanel
          chapter={selection.data as ProjectChapter}
          project={project}
          allEngines={allEngines}
          allVoices={allVoices}
          onRefresh={onRefresh}
        />
      )}

      {selection.type === "section" && (
        <SectionDetailPanel section={selection.data as ProjectSection} />
      )}

      {selection.type === "chunk" && (
        <ChunkDetailPanel
          chunk={selection.data as ProjectChunk}
          project={project}
          onRefresh={onRefresh}
        />
      )}

      <Separator />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Audio Generation</h3>
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
        <ProjectAudioList audioFiles={audioFiles} projectId={project.id} />
      </div>
    </div>
  );
}

function ProjectSettingsPanel({
  project,
  allEngines,
  allVoices,
  onRefresh,
}: {
  project: ProjectData;
  allEngines: { id: string; label: string }[];
  allVoices: { id: string; label: string }[];
  onRefresh: () => void;
}) {
  const { toast } = useToast();
  const [ttsEngine, setTtsEngine] = useState(project.ttsEngine || "edge-tts");
  const [narratorVoice, setNarratorVoice] = useState(project.narratorVoiceId || "");
  const [exaggeration, setExaggeration] = useState(project.exaggeration ?? 0.5);
  const [pauseDuration, setPauseDuration] = useState(project.pauseDuration ?? 500);

  useEffect(() => {
    setTtsEngine(project.ttsEngine || "edge-tts");
    setNarratorVoice(project.narratorVoiceId || "");
    setExaggeration(project.exaggeration ?? 0.5);
    setPauseDuration(project.pauseDuration ?? 500);
  }, [project.id]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      await apiRequest("PATCH", `/api/projects/${project.id}`, {
        ttsEngine: ttsEngine,
        narratorVoiceId: narratorVoice || null,
        exaggeration,
        pauseDuration,
      });
    },
    onSuccess: () => {
      toast({ title: "Settings saved" });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Failed to save", description: error.message, variant: "destructive" });
    },
  });

  const chapters = project.chapters || [];
  const totalChunks = chapters.reduce(
    (sum, ch) => sum + (ch.sections || []).reduce((s, sec) => s + (sec.chunks?.length || 0), 0),
    0
  );

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

      <Separator />

      <div className="grid gap-4">
        <div className="space-y-2">
          <Label>TTS Engine</Label>
          <Select value={ttsEngine} onValueChange={setTtsEngine}>
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
          <Label>Narrator Voice</Label>
          <Select value={narratorVoice} onValueChange={setNarratorVoice}>
            <SelectTrigger data-testid="select-narrator-voice">
              <SelectValue placeholder="Select a voice..." />
            </SelectTrigger>
            <SelectContent>
              {allVoices.map((v) => (
                <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
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

        <Button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          data-testid="button-save-settings"
        >
          <Save className="h-4 w-4 mr-2" />
          {saveMutation.isPending ? "Saving..." : "Save Settings"}
        </Button>
      </div>
    </div>
  );
}

function ChapterDetailPanel({
  chapter,
  project,
  allEngines,
  allVoices,
  onRefresh,
}: {
  chapter: ProjectChapter;
  project: ProjectData;
  allEngines: { id: string; label: string }[];
  allVoices: { id: string; label: string }[];
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
              <SelectItem value="__default__">Use book default</SelectItem>
              {allVoices.map((v) => (
                <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>
              ))}
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

function SectionDetailPanel({ section }: { section: ProjectSection }) {
  const chunks = section.chunks || [];
  const totalWords = chunks.reduce((sum, c) => sum + (c.wordCount || 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <FileText className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-bold" data-testid="text-detail-title">
          Section {section.sectionIndex + 1}
        </h2>
        <Badge variant="outline">{section.status}</Badge>
      </div>
      <div className="flex gap-4 text-sm text-muted-foreground">
        <span>{chunks.length} chunks</span>
        <span>{totalWords} words</span>
      </div>
    </div>
  );
}

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
      await apiRequest("PATCH", `/api/projects/${project.id}/chunks/${chunk.id}`, {
        speakerOverride: speakerOverride && speakerOverride !== "__auto__" ? speakerOverride : null,
        emotionOverride: emotionOverride && emotionOverride !== "__auto__" ? emotionOverride : null,
      });
    },
    onSuccess: () => {
      toast({ title: "Chunk overrides saved" });
      onRefresh();
    },
    onError: (error: Error) => {
      toast({ title: "Failed to save", description: error.message, variant: "destructive" });
    },
  });

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
      </div>
    </div>
  );
}
