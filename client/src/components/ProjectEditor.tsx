import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ProjectTree, type TreeSelection } from "@/components/ProjectTree";
import { ProjectDetailPanel } from "@/components/ProjectDetailPanel";
import type { ProjectData } from "@shared/schema";

interface ProjectEditorProps {
  projectId: string;
  onBack: () => void;
}

export function ProjectEditor({ projectId, onBack }: ProjectEditorProps) {
  const queryClient = useQueryClient();
  const [selection, setSelection] = useState<TreeSelection | null>(null);

  const {
    data: project,
    isLoading,
    error,
  } = useQuery<ProjectData>({
    queryKey: ["/api/projects", projectId],
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.status === "segmenting" || data.status === "generating")) {
        return 2000;
      }
      return false;
    },
  });

  useEffect(() => {
    if (project && !selection) {
      setSelection({ type: "project", id: project.id, data: project });
    }
  }, [project]);

  useEffect(() => {
    if (project && selection) {
      if (selection.type === "project") {
        setSelection({ ...selection, data: project });
      } else if (selection.type === "chapter") {
        const ch = (project.chapters || []).find((c) => c.id === selection.id);
        if (ch) setSelection({ ...selection, data: ch });
      } else if (selection.type === "section") {
        for (const ch of project.chapters || []) {
          const sec = (ch.sections || []).find((s) => s.id === selection.id);
          if (sec) {
            setSelection({ ...selection, data: sec });
            break;
          }
        }
      } else if (selection.type === "chunk") {
        for (const ch of project.chapters || []) {
          for (const sec of ch.sections || []) {
            const chunk = (sec.chunks || []).find((c) => c.id === selection.id);
            if (chunk) {
              setSelection({ ...selection, data: chunk });
              break;
            }
          }
        }
      }
    }
  }, [project]);

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["/api/projects", projectId] });
  };

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto space-y-4">
        <Skeleton className="h-10 w-32" />
        <div className="grid grid-cols-12 gap-4">
          <Skeleton className="col-span-4 h-96" />
          <Skeleton className="col-span-8 h-96" />
        </div>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="max-w-6xl mx-auto space-y-4">
        <Button variant="ghost" onClick={onBack} data-testid="button-back-to-list">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Projects
        </Button>
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <AlertCircle className="h-12 w-12 text-destructive mb-4" />
            <h3 className="text-lg font-semibold">Failed to load project</h3>
            <p className="text-sm text-muted-foreground">{(error as Error)?.message || "Project not found"}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-4" data-testid="project-editor">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} data-testid="button-back-to-list">
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
        <h1 className="text-xl font-bold truncate" data-testid="text-project-title">{project.title}</h1>
        {(project.status === "segmenting" || project.status === "generating") && (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        )}
      </div>

      <div className="grid grid-cols-12 gap-4">
        <Card className="col-span-12 md:col-span-4">
          <ScrollArea className="h-[calc(100vh-200px)]">
            <div className="p-3">
              <ProjectTree
                project={project}
                selection={selection}
                onSelect={setSelection}
              />
            </div>
          </ScrollArea>
        </Card>

        <Card className="col-span-12 md:col-span-8">
          <ScrollArea className="h-[calc(100vh-200px)]">
            <div className="p-4">
              {selection ? (
                <ProjectDetailPanel
                  selection={selection}
                  project={project}
                  onRefresh={handleRefresh}
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
    </div>
  );
}
