import { useState, useCallback, useRef } from "react";
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
  selectedChunkIds: Set<string>;
  onSelect: (selection: TreeSelection) => void;
  onMultiSelect: (chunkIds: Set<string>, chunks: ProjectChunk[]) => void;
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
  onClick: (e: React.MouseEvent) => void;
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

export function ProjectTree({ project, selection, selectedChunkIds, onSelect, onMultiSelect }: ProjectTreeProps) {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set(["project"]));
  const lastClickedChunkRef = useRef<string | null>(null);

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

  const allChunksFlat = useCallback((): ProjectChunk[] => {
    const result: ProjectChunk[] = [];
    for (const ch of project.chapters || []) {
      for (const sec of ch.sections || []) {
        for (const chunk of sec.chunks || []) {
          result.push(chunk);
        }
      }
    }
    return result;
  }, [project]);

  const handleChunkClick = useCallback((e: React.MouseEvent, chunk: ProjectChunk) => {
    const isCtrl = e.ctrlKey || e.metaKey;
    const isShift = e.shiftKey;

    if (isCtrl) {
      const newSet = new Set(selectedChunkIds);
      if (newSet.size === 0 && selection?.type === "chunk" && selection.id !== chunk.id) {
        newSet.add(selection.id);
      }
      if (newSet.has(chunk.id)) {
        newSet.delete(chunk.id);
      } else {
        newSet.add(chunk.id);
      }
      lastClickedChunkRef.current = chunk.id;

      if (newSet.size === 1) {
        const remainingId = Array.from(newSet)[0];
        const all = allChunksFlat();
        const remainingChunk = all.find(c => c.id === remainingId);
        if (remainingChunk) {
          onSelect({ type: "chunk", id: remainingId, data: remainingChunk });
          onMultiSelect(new Set(), []);
        }
      } else if (newSet.size === 0) {
        onMultiSelect(new Set(), []);
      } else {
        const all = allChunksFlat();
        const selectedChunks = all.filter(c => newSet.has(c.id));
        onMultiSelect(newSet, selectedChunks);
      }
    } else if (isShift && lastClickedChunkRef.current) {
      const all = allChunksFlat();
      const lastIdx = all.findIndex(c => c.id === lastClickedChunkRef.current);
      const currentIdx = all.findIndex(c => c.id === chunk.id);
      if (lastIdx >= 0 && currentIdx >= 0) {
        const start = Math.min(lastIdx, currentIdx);
        const end = Math.max(lastIdx, currentIdx);
        const rangeChunks = all.slice(start, end + 1);
        const newSet = new Set(selectedChunkIds);
        for (const c of rangeChunks) {
          newSet.add(c.id);
        }
        const selectedChunks = all.filter(c => newSet.has(c.id));
        onMultiSelect(newSet, selectedChunks);
      }
    } else {
      lastClickedChunkRef.current = chunk.id;
      onMultiSelect(new Set(), []);
      onSelect({ type: "chunk", id: chunk.id, data: chunk });
    }
  }, [selectedChunkIds, selection, onSelect, onMultiSelect, allChunksFlat]);

  const handleNonChunkClick = useCallback((sel: TreeSelection) => {
    lastClickedChunkRef.current = null;
    onMultiSelect(new Set(), []);
    onSelect(sel);
  }, [onSelect, onMultiSelect]);

  const chapters = project.chapters || [];
  const isProjectExpanded = expandedNodes.has("project");

  return (
    <div className="space-y-0.5 text-sm" data-testid="project-tree">
      <TreeNode
        icon={Book}
        label={project.title}
        sublabel={`${chapters.length} ch`}
        status={project.status}
        isSelected={selectedChunkIds.size === 0 && selection?.type === "project" && selection.id === project.id}
        isExpanded={isProjectExpanded}
        hasChildren={chapters.length > 0}
        depth={0}
        onClick={() => handleNonChunkClick({ type: "project", id: project.id, data: project })}
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
                isSelected={selectedChunkIds.size === 0 && selection?.type === "chapter" && selection.id === chapter.id}
                isExpanded={isChapterExpanded}
                hasChildren={sections.length > 0}
                depth={1}
                onClick={() => handleNonChunkClick({ type: "chapter", id: chapter.id, data: chapter })}
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
                        label={section.title ? `Sec ${section.sectionIndex + 1}: ${section.title}` : `Sec ${section.sectionIndex + 1}`}
                        sublabel={`${chunks.length} chunks`}
                        status={section.status}
                        isSelected={selectedChunkIds.size === 0 && selection?.type === "section" && selection.id === section.id}
                        isExpanded={isSectionExpanded}
                        hasChildren={chunks.length > 0}
                        depth={2}
                        onClick={() => handleNonChunkClick({ type: "section", id: section.id, data: section })}
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
                            isSelected={
                              selectedChunkIds.has(chunk.id) ||
                              (selectedChunkIds.size === 0 && selection?.type === "chunk" && selection.id === chunk.id)
                            }
                            hasChildren={false}
                            depth={3}
                            onClick={(e) => handleChunkClick(e, chunk)}
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
