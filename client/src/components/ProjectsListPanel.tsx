import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Book, Calendar, Layers, FileText, ChevronRight, Loader2, Trash2, Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
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
import { CreateProjectDialog } from "@/components/CreateProjectDialog";
import { useToast } from "@/hooks/use-toast";
import type { ProjectListItem, ProjectData, GenerationProgress, SegmentationProgress } from "@shared/schema";

interface ProjectsListPanelProps {
  onSelectProject: (projectId: string) => void;
}

function formatSegEta(progress: SegmentationProgress): string | null {
  const { processedBytes, totalBytes, startedAt } = progress;
  const remaining = totalBytes - processedBytes;
  if (remaining <= 0 || !startedAt || processedBytes === 0) return null;

  const elapsedMs = Date.now() - new Date(startedAt).getTime();
  if (elapsedMs <= 0) return null;

  const ratePerMs = processedBytes / elapsedMs;
  const etaMs = remaining / ratePerMs;
  const etaMins = Math.round(etaMs / 60_000);

  if (etaMins < 1) return "< 1 min remaining";
  if (etaMins === 1) return "~1 min remaining";
  return `~${etaMins} min remaining`;
}

function formatEta(progress: GenerationProgress): string | null {
  const { completedChunks, failedChunks, totalChunks, firstCompletedAt } = progress;
  const remaining = totalChunks - completedChunks - failedChunks;
  if (remaining <= 0) return null;
  if (!firstCompletedAt || completedChunks === 0) return null;

  const elapsedMs = Date.now() - new Date(firstCompletedAt).getTime();
  if (elapsedMs <= 0) return null;

  const ratePerMs = completedChunks / elapsedMs;
  const etaMs = remaining / ratePerMs;
  const etaMins = Math.round(etaMs / 60_000);

  if (etaMins < 1) return "< 1 min remaining";
  if (etaMins === 1) return "~1 min remaining";
  return `~${etaMins} min remaining`;
}

const statusColors: Record<string, string> = {
  draft: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300",
  segmenting: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
  segmented: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
  generating: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300",
  completed: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300",
};

export function ProjectsListPanel({ onSelectProject }: ProjectsListPanelProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [deleteTarget, setDeleteTarget] = useState<ProjectListItem | null>(null);

  const { data: projects = [], isLoading } = useQuery<ProjectListItem[]>({
    queryKey: ["/api/projects"],
    refetchInterval: 5000,
  });

  const deleteMutation = useMutation({
    mutationFn: async (projectId: string) => {
      const res = await fetch(`/api/projects/${projectId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) throw new Error(await res.text());
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      toast({ title: "Project deleted" });
      setDeleteTarget(null);
    },
    onError: (error: Error) => {
      toast({ title: "Failed to delete project", description: error.message, variant: "destructive" });
      setDeleteTarget(null);
    },
  });

  const handleProjectCreated = (project: ProjectData) => {
    onSelectProject(project.id);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold" data-testid="text-projects-heading">Projects</h2>
          <p className="text-muted-foreground text-sm">Manage your audiobook projects</p>
        </div>
        <CreateProjectDialog onProjectCreated={handleProjectCreated} />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <Book className="h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-1">No projects yet</h3>
            <p className="text-sm text-muted-foreground mb-4">Create your first audiobook project to get started.</p>
            <CreateProjectDialog onProjectCreated={handleProjectCreated} />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {projects.map((project) => (
            <Card
              key={project.id}
              className="cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => onSelectProject(project.id)}
              data-testid={`card-project-${project.id}`}
            >
              <CardContent className="flex items-center justify-between p-4">
                <div className="flex items-center gap-4 min-w-0">
                  <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    <Book className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="font-semibold truncate" data-testid={`text-project-title-${project.id}`}>
                      {project.title}
                    </h3>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                      <span className="flex items-center gap-1">
                        <Layers className="h-3 w-3" />
                        {project.chapterCount} {project.chapterCount === 1 ? "chapter" : "chapters"}
                      </span>
                      <span className="flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {project.totalChunks} chunks
                      </span>
                      {project.createdAt && (
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {new Date(project.createdAt).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    {project.segmentationProgress && (() => {
                      const sp = project.segmentationProgress!;
                      const pct = sp.totalBytes > 0
                        ? Math.round((sp.processedBytes / sp.totalBytes) * 100)
                        : 0;
                      const eta = formatSegEta(sp);
                      return (
                        <div className="mt-2 space-y-1">
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              Segmenting… {pct}%
                            </span>
                            {eta && (
                              <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {eta}
                              </span>
                            )}
                          </div>
                          <Progress value={pct} className="h-1.5" />
                        </div>
                      );
                    })()}
                    {project.generationProgress && (() => {
                      const gp = project.generationProgress!;
                      const pct = gp.totalChunks > 0
                        ? Math.round(((gp.completedChunks + gp.failedChunks) / gp.totalChunks) * 100)
                        : 0;
                      const eta = formatEta(gp);
                      return (
                        <div className="mt-2 space-y-1">
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span className="flex items-center gap-1">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              {gp.completedChunks}/{gp.totalChunks} chunks ({pct}%)
                            </span>
                            {eta && (
                              <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {eta}
                              </span>
                            )}
                          </div>
                          <Progress value={pct} className="h-1.5" />
                        </div>
                      );
                    })()}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {project.generationProgress ? (
                    <Badge variant="outline" className={statusColors["generating"]}>
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      generating
                    </Badge>
                  ) : (
                    <Badge variant="outline" className={statusColors[project.status] || ""}>
                      {project.status === "segmenting" && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                      {project.status}
                    </Badge>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteTarget(project);
                    }}
                    data-testid={`button-delete-project-${project.id}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete "{deleteTarget?.title}" and all its chapters, sections, chunks, and generated audio. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="button-cancel-delete">Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
              data-testid="button-confirm-delete"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
