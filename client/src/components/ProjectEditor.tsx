import { useState, useEffect, useCallback, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, AlertCircle, Archive, Save, Wand2, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ProjectTree, type TreeSelection, type ValidationTreeData } from "@/components/ProjectTree";
import { ProjectDetailPanel } from "@/components/ProjectDetailPanel";
import { BulkOverridePanel } from "@/components/BulkOverridePanel";
import { ValidationMultiSelectPanel } from "@/components/ValidationMultiSelectPanel";
import { BackupProjectDialog } from "@/components/BackupProjectDialog";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { ProjectData, ProjectChunk } from "@shared/schema";

interface ProjectEditorProps {
  projectId: string;
  onBack: () => void;
}

export function ProjectEditor({ projectId, onBack }: ProjectEditorProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [selection, setSelection] = useState<TreeSelection | null>(null);
  const [selectedChunkIds, setSelectedChunkIds] = useState<Set<string>>(new Set());
  const [selectedChunks, setSelectedChunks] = useState<ProjectChunk[]>([]);
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false);
  const [generateAfterSave, setGenerateAfterSave] = useState(false);
  const [selectedValidationChunkIds, setSelectedValidationChunkIds] = useState<Set<string>>(new Set());

  const settingsPanelRef = useRef<{ save: () => void; isDirty: () => boolean } | null>(null);

  const [treeWidth, setTreeWidth] = useState(320);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    isDragging.current = true;
    dragStartX.current = e.clientX;
    dragStartWidth.current = treeWidth;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [treeWidth]);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      const delta = e.clientX - dragStartX.current;
      setTreeWidth(Math.min(600, Math.max(200, dragStartWidth.current + delta)));
    };
    const onUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const { data: project, isLoading, error } = useQuery<ProjectData>({
    queryKey: ["/api/projects", projectId],
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.status === "segmenting" || data.status === "generating")) { return 2000; }
      return false;
    },
  });

  const { data: validationResultsData } = useQuery<{
    results: Array<{ chunkId: string; chunkText: string; combinedScore: number; isFlagged: boolean; isRegenerated: boolean }>;
    jobStatus: string | null;
    jobId: string | null;
    jobProgress: number;
  }>({
    queryKey: ["/api/projects", projectId, "validation/results"],
    refetchInterval: (query) => {
      const status = query.state.data?.jobStatus;
      return status === "processing" || status === "pending" ? 3000 : false;
    },
  });

  const validationData: ValidationTreeData = {
    flaggedChunks: (validationResultsData?.results ?? [])
      .filter((r) => r.isFlagged && !r.isRegenerated)
      .map((r) => ({ chunkId: r.chunkId, chunkText: r.chunkText, combinedScore: r.combinedScore })),
    activeJobStatus: validationResultsData?.jobStatus ?? null,
    totalValidated: validationResultsData?.results.length ?? 0,
    hasResults: (validationResultsData?.results.length ?? 0) > 0,
  };

  useEffect(() => {
    if (project && !selection) {
      setSelection({ type: "project", id: project.id, data: project });
    }
  }, [project]);

  useEffect(() => {
    if (project && selection) {
      if (selection.type === "project") {
        setSelection({ ...selection, data: project });
      } else if (selection.type === "engine-settings" || selection.type === "voice-settings" || selection.type === "characters" || selection.type === "output-files" || selection.type === "book-content") {
        setSelection({ ...selection, data: project });
      } else if (selection.type === "chapter") {
        const ch = (project.chapters || []).find((c) => c.id === selection.id);
        if (ch) setSelection({ ...selection, data: ch });
      } else if (selection.type === "section") {
        for (const ch of project.chapters || []) {
          const sec = (ch.sections || []).find((s) => s.id === selection.id);
          if (sec) { setSelection({ ...selection, data: sec }); break; }
        }
      } else if (selection.type === "chunk") {
        for (const ch of project.chapters || []) {
          for (const sec of ch.sections || []) {
            const chunk = (sec.chunks || []).find((c) => c.id === selection.id);
            if (chunk) { setSelection({ ...selection, data: chunk }); break; }
          }
        }
      }
    }
  }, [project]);

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["/api/projects", projectId] });
  };

  const handleMultiSelect = useCallback((chunkIds: Set<string>, chunks: ProjectChunk[]) => {
    setSelectedChunkIds(chunkIds);
    setSelectedChunks(chunks);
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedChunkIds(new Set());
    setSelectedChunks([]);
  }, []);

  const handleClearValidationSelection = useCallback(() => {
    setSelectedValidationChunkIds(new Set());
  }, []);

  const handleGenerateProject = async () => {
    if (!project) return;
    try {
      const res = await apiRequest("POST", `/api/projects/${project.id}/generate`, {
        scopeType: "project",
        scopeId: project.id,
        onlyMissing: false,
      });
      const data = await res.json();
      if (data.message) {
        toast({ title: "Nothing to generate", description: data.message });
      } else {
        const jobCount = data.totalJobs || 1;
        const desc = jobCount > 1
          ? `${jobCount} section jobs created with ${data.totalSegments} total segments. Check the Jobs tab for progress.`
          : `Job created with ${data.totalSegments} segments. Check the Jobs tab for progress.`;
        toast({ title: "Generation started", description: desc });
      }
      handleRefresh();
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
    } catch (error: any) {
      toast({ title: "Generation failed", description: error.message, variant: "destructive" });
    }
  };

  const handleExportAudio = async () => {
    if (!project) return;
    settingsPanelRef.current?.save();
    try {
      await apiRequest("POST", `/api/projects/${project.id}/export`, {});
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
      toast({ title: "Export job started", description: "Check the Jobs tab for progress and download." });
    } catch (error: any) {
      toast({ title: "Export failed", description: error.message, variant: "destructive" });
    }
  };

  const handleGenerateClick = () => {
    if (!project) return;
    const dirty = settingsPanelRef.current?.isDirty() ?? false;
    if (dirty) {
      setShowUnsavedDialog(true);
    } else {
      handleGenerateProject();
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto space-y-4" data-testid="project-editor-loading">
        <div className="flex items-center gap-3">
          <div className="h-8 w-16 bg-muted animate-pulse rounded" />
          <div className="h-6 w-48 bg-muted animate-pulse rounded" />
        </div>
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-4 h-96 bg-muted animate-pulse rounded-lg" />
          <div className="col-span-8 h-96 bg-muted animate-pulse rounded-lg" />
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="max-w-6xl mx-auto" data-testid="project-editor-error">
        <div className="flex items-center gap-3 p-4 border border-destructive/50 rounded-lg text-destructive">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <p className="text-sm">Failed to load project. Please try again.</p>
        </div>
      </div>
    );
  }

  const showBulkPanel = selectedChunkIds.size > 1;
  const showValidationMultiPanel = selectedValidationChunkIds.size > 1;
  const hasGeneratedAudio = (project.audioFiles || []).some(af => af.scopeType !== "export");
  const isSegmenting = project.status === "segmenting";

  return (
    <div className="max-w-6xl mx-auto space-y-4" data-testid="project-editor">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} data-testid="button-back-to-list">
          <ArrowLeft className="h-4 w-4 mr-2" />Back
        </Button>
        <h1 className="text-xl font-bold truncate" data-testid="text-project-title">{project.title}</h1>
        {(project.status === "segmenting" || project.status === "generating") && (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        )}
        <div className="ml-auto">
          <BackupProjectDialog project={project} iconOnly />
        </div>
      </div>

      <div className="flex gap-0 items-stretch">
        <Card className="flex flex-col h-[calc(100vh-200px)] shrink-0" style={{ width: treeWidth }}>
          <ScrollArea className="flex-1 overflow-hidden">
            <div className="p-3">
              <ProjectTree
                project={project}
                selection={selection}
                selectedChunkIds={selectedChunkIds}
                onSelect={(sel) => { if (sel.type !== "validation-chunk") setSelectedValidationChunkIds(new Set()); setSelection(sel); }}
                onMultiSelect={(ids, chunks) => { setSelectedValidationChunkIds(new Set()); handleMultiSelect(ids, chunks); }}
                validationData={validationData}
                selectedValidationChunkIds={selectedValidationChunkIds}
                onValidationMultiSelect={setSelectedValidationChunkIds}
              />
            </div>
          </ScrollArea>
          <div className="p-3 border-t shrink-0 flex flex-col gap-2">
            <Button
              variant="default"
              size="sm"
              className="w-full"
              disabled={isSegmenting}
              onClick={() => settingsPanelRef.current?.save()}
              data-testid="button-save-settings"
            >
              <Save className="h-3.5 w-3.5 mr-2" />
              Save Settings
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              disabled={isSegmenting}
              onClick={handleGenerateClick}
              data-testid="button-generate-project"
            >
              <Wand2 className="h-3.5 w-3.5 mr-2" />
              Generate Project
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              disabled={isSegmenting || !hasGeneratedAudio}
              onClick={handleExportAudio}
              data-testid="button-export-audio"
            >
              <Download className="h-3.5 w-3.5 mr-2" />
              Export Audio
            </Button>
          </div>
        </Card>

        {/* Drag handle */}
        <div
          className="w-1.5 shrink-0 cursor-col-resize hover:bg-primary/30 active:bg-primary/50 transition-colors mx-1 rounded-full"
          onMouseDown={handleDragStart}
        />

        <Card className="flex-1 min-w-0">
          <ScrollArea className="h-[calc(100vh-200px)]">
            <div className="p-4">
              {showValidationMultiPanel ? (
                <ValidationMultiSelectPanel
                  selectedIds={selectedValidationChunkIds}
                  project={project}
                  onRefresh={handleRefresh}
                  onClearSelection={handleClearValidationSelection}
                />
              ) : showBulkPanel ? (
                <BulkOverridePanel
                  selectedChunks={selectedChunks}
                  selectedChunkIds={selectedChunkIds}
                  project={project}
                  onRefresh={handleRefresh}
                  onClearSelection={handleClearSelection}
                />
              ) : selection ? (
                <ProjectDetailPanel
                  selection={selection}
                  project={project}
                  onRefresh={handleRefresh}
                  settingsPanelRef={settingsPanelRef}
                />
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
                  <p>Select a node from the tree to view details</p>
                </div>
              )}
            </div>
          </ScrollArea>
        </Card>
      </div>

      <AlertDialog open={showUnsavedDialog} onOpenChange={setShowUnsavedDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unsaved Settings Changes</AlertDialogTitle>
            <AlertDialogDescription>
              You have unsaved settings changes. Save them before generating?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setShowUnsavedDialog(false);
                handleGenerateProject();
              }}
            >
              Generate with saved settings
            </AlertDialogAction>
            <AlertDialogAction
              onClick={() => {
                setShowUnsavedDialog(false);
                settingsPanelRef.current?.save();
                handleGenerateProject();
              }}
            >
              Save &amp; Generate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
