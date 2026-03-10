import { useState } from "react";
import { ChevronRight, ChevronDown, Book, FileText, Layers, Type, Loader2, CheckCircle2, AlertCircle, Volume2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ProjectData, ProjectChapter, ProjectSection, ProjectChunk } from "@shared/schema";

export type TreeNodeType = "project" | "chapter" | "section" | "chunk";

export interface TreeSelection {
  type: TreeNodeType;
  id: string;
  data: ProjectData | ProjectChapter | ProjectSection | ProjectChunk;
}

interface ProjectTreeProps {
  project: ProjectData;
  selection: TreeSelection | null;
  onSelect: (selection: TreeSelection) => void;
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "pending":
    case "draft":
      return <div className="h-2 w-2 rounded-full bg-gray-400" />;
    case "segmenting":
      return <Loader2 className="h-3 w-3 text-blue-500 animate-spin" />;
    case "segmented":
      return <CheckCircle2 className="h-3 w-3 text-green-500" />;
    case "generating":
      return <Loader2 className="h-3 w-3 text-yellow-500 animate-spin" />;
    case "completed":
      return <CheckCircle2 className="h-3 w-3 text-purple-500" />;
    case "failed":
      return <AlertCircle className="h-3 w-3 text-red-500" />;
    default:
      return <div className="h-2 w-2 rounded-full bg-gray-400" />;
  }
}

function TreeNode({
  icon: Icon,
  label,
  sublabel,
  status,
  isSelected,
  isExpanded,
  hasChildren,
  depth,
  onClick,
  onToggle,
  testId,
}: {
  icon: any;
  label: string;
  sublabel?: string;
  status: string;
  isSelected: boolean;
  isExpanded?: boolean;
  hasChildren: boolean;
  depth: number;
  onClick: () => void;
  onToggle?: () => void;
  testId: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1 py-1 px-2 rounded-md cursor-pointer text-sm transition-colors",
        isSelected
          ? "bg-primary/10 text-primary font-medium"
          : "hover:bg-muted/50"
      )}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
      onClick={onClick}
      data-testid={testId}
    >
      {hasChildren ? (
        <button
          className="p-0.5 hover:bg-muted rounded shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.();
          }}
          data-testid={`toggle-${testId}`}
        >
          {isExpanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
        </button>
      ) : (
        <span className="w-4" />
      )}
      <StatusIcon status={status} />
      <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate">{label}</span>
      {sublabel && (
        <span className="text-xs text-muted-foreground ml-auto shrink-0">{sublabel}</span>
      )}
    </div>
  );
}

export function ProjectTree({ project, selection, onSelect }: ProjectTreeProps) {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(["project"]));

  const toggleNode = (id: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const chapters = project.chapters || [];
  const isProjectExpanded = expandedNodes.has("project");

  return (
    <div className="space-y-0.5 text-sm" data-testid="project-tree">
      <TreeNode
        icon={Book}
        label={project.title}
        sublabel={`${chapters.length} ch`}
        status={project.status}
        isSelected={selection?.type === "project" && selection.id === project.id}
        isExpanded={isProjectExpanded}
        hasChildren={chapters.length > 0}
        depth={0}
        onClick={() => onSelect({ type: "project", id: project.id, data: project })}
        onToggle={() => toggleNode("project")}
        testId="tree-project"
      />

      {isProjectExpanded &&
        chapters.map((chapter) => {
          const chapterId = `ch-${chapter.id}`;
          const isChapterExpanded = expandedNodes.has(chapterId);
          const sections = chapter.sections || [];
          const chunkCount = sections.reduce(
            (sum, s) => sum + (s.chunks?.length || 0),
            0
          );

          return (
            <div key={chapter.id}>
              <TreeNode
                icon={Layers}
                label={chapter.title || `Chapter ${chapter.chapterIndex + 1}`}
                sublabel={`${chunkCount} chunks`}
                status={chapter.status}
                isSelected={selection?.type === "chapter" && selection.id === chapter.id}
                isExpanded={isChapterExpanded}
                hasChildren={sections.length > 0}
                depth={1}
                onClick={() => onSelect({ type: "chapter", id: chapter.id, data: chapter })}
                onToggle={() => toggleNode(chapterId)}
                testId={`tree-chapter-${chapter.id}`}
              />

              {isChapterExpanded &&
                sections.map((section) => {
                  const sectionId = `sec-${section.id}`;
                  const isSectionExpanded = expandedNodes.has(sectionId);
                  const chunks = section.chunks || [];

                  return (
                    <div key={section.id}>
                      <TreeNode
                        icon={FileText}
                        label={`Section ${section.sectionIndex + 1}`}
                        sublabel={`${chunks.length} chunks`}
                        status={section.status}
                        isSelected={selection?.type === "section" && selection.id === section.id}
                        isExpanded={isSectionExpanded}
                        hasChildren={chunks.length > 0}
                        depth={2}
                        onClick={() => onSelect({ type: "section", id: section.id, data: section })}
                        onToggle={() => toggleNode(sectionId)}
                        testId={`tree-section-${section.id}`}
                      />

                      {isSectionExpanded &&
                        chunks.map((chunk) => (
                          <TreeNode
                            key={chunk.id}
                            icon={Type}
                            label={chunk.text.substring(0, 50) + (chunk.text.length > 50 ? "..." : "")}
                            sublabel={chunk.emotion || undefined}
                            status="segmented"
                            isSelected={selection?.type === "chunk" && selection.id === chunk.id}
                            hasChildren={false}
                            depth={3}
                            onClick={() => onSelect({ type: "chunk", id: chunk.id, data: chunk })}
                            testId={`tree-chunk-${chunk.id}`}
                          />
                        ))}
                    </div>
                  );
                })}
            </div>
          );
        })}
    </div>
  );
}
