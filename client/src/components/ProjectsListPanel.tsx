import { useQuery } from "@tanstack/react-query";
import { Book, Calendar, Layers, FileText, ChevronRight, Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CreateProjectDialog } from "@/components/CreateProjectDialog";
import type { ProjectListItem, ProjectData } from "@shared/schema";

interface ProjectsListPanelProps {
  onSelectProject: (projectId: string) => void;
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
  const { data: projects = [], isLoading } = useQuery<ProjectListItem[]>({
    queryKey: ["/api/projects"],
    refetchInterval: 5000,
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
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <Badge variant="outline" className={statusColors[project.status] || ""}>
                    {project.status === "segmenting" && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
                    {project.status}
                  </Badge>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
