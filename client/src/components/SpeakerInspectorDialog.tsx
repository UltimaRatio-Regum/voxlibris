import { useState, useMemo, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Users, Check, Square, SquareCheck, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { ProjectData, ProjectChunk } from "@shared/schema";

const UNASSIGNED_SENTINEL = "__unassigned__";

interface ContextPiece {
  text: string;
  isDialogue: boolean;
}

interface ChunkWithContext {
  chunkId: string;
  chapterTitle: string;
  sectionIndex: number;
  chunkIndex: number;
  text: string;
  contextBefore: ContextPiece | null;
  contextAfter: ContextPiece | null;
  segmentType: string;
  emotion: string | null;
  originalSpeaker: string;
}

interface SpeakerInspectorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  speakerName: string;
  project: ProjectData;
  allSpeakers: string[];
  onMergeComplete: () => void;
}

function wrapInQuotes(text: string, isDialogue: boolean): string {
  return isDialogue ? `\u201c${text}\u201d` : text;
}

function getChunksForSpeaker(project: ProjectData, speakerName: string): ChunkWithContext[] {
  const results: ChunkWithContext[] = [];
  const isUnassigned = speakerName === UNASSIGNED_SENTINEL;

  for (const chapter of project.chapters || []) {
    for (const section of chapter.sections || []) {
      const chunks = section.chunks || [];
      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        const effectiveSpeaker = chunk.speakerOverride || chunk.speaker;

        if (isUnassigned) {
          if (chunk.segmentType !== "dialogue" || effectiveSpeaker) continue;
        } else {
          if (effectiveSpeaker !== speakerName) continue;
        }

        const prevChunk = i > 0 ? chunks[i - 1] : null;
        const nextChunk = i < chunks.length - 1 ? chunks[i + 1] : null;

        const contextBefore = prevChunk ? {
          text: prevChunk.text.length > 150 ? "..." + prevChunk.text.slice(-150) : prevChunk.text,
          isDialogue: prevChunk.segmentType === "dialogue",
        } : null;

        const contextAfter = nextChunk ? {
          text: nextChunk.text.length > 150 ? nextChunk.text.slice(0, 150) + "..." : nextChunk.text,
          isDialogue: nextChunk.segmentType === "dialogue",
        } : null;

        results.push({
          chunkId: chunk.id,
          chapterTitle: chapter.title || `Chapter ${chapter.chapterIndex + 1}`,
          sectionIndex: section.sectionIndex,
          chunkIndex: i,
          text: chunk.text,
          contextBefore,
          contextAfter,
          segmentType: chunk.segmentType || "narration",
          emotion: chunk.emotion || null,
          originalSpeaker: isUnassigned ? "" : speakerName,
        });
      }
    }
  }

  return results;
}

export function SpeakerInspectorDialog({
  open,
  onOpenChange,
  speakerName,
  project,
  allSpeakers,
  onMergeComplete,
}: SpeakerInspectorDialogProps) {
  const { toast } = useToast();
  const [selectedChunks, setSelectedChunks] = useState<Set<string>>(new Set());
  const [chunkSpeakerMap, setChunkSpeakerMap] = useState<Record<string, string>>({});
  const [customSpeakers, setCustomSpeakers] = useState<string[]>([]);
  const [bulkTarget, setBulkTarget] = useState("__placeholder__");
  const [newBulkSpeakerName, setNewBulkSpeakerName] = useState("");
  const [newRowSpeakerNames, setNewRowSpeakerNames] = useState<Record<string, string>>({});

  const isUnassigned = speakerName === UNASSIGNED_SENTINEL;

  useEffect(() => {
    if (open) {
      setSelectedChunks(new Set());
      setChunkSpeakerMap({});
      setCustomSpeakers([]);
      setBulkTarget("__placeholder__");
      setNewBulkSpeakerName("");
      setNewRowSpeakerNames({});
    }
  }, [open, speakerName]);

  const chunks = getChunksForSpeaker(project, speakerName);

  const RESERVED_NAMES = ["__new__", "__placeholder__", "__existing__", UNASSIGNED_SENTINEL];

  const isValidSpeakerName = (name: string): boolean => {
    const trimmed = name.trim();
    return trimmed.length > 0 && !RESERVED_NAMES.includes(trimmed);
  };

  const allAvailableSpeakers = useMemo(() => {
    const combined = new Set([...allSpeakers, ...customSpeakers]);
    return Array.from(combined).sort();
  }, [allSpeakers, customSpeakers]);

  const getOriginalSpeaker = (chunkId: string) => {
    return isUnassigned ? "" : speakerName;
  };

  const getSpeakerForChunk = (chunkId: string) => {
    return chunkSpeakerMap[chunkId] || getOriginalSpeaker(chunkId);
  };

  const hasChanges = useMemo(() => {
    return chunks.some((chunk) => {
      const current = chunkSpeakerMap[chunk.chunkId];
      if (isUnassigned) return !!current;
      return current !== undefined && current !== speakerName;
    });
  }, [chunkSpeakerMap, chunks, speakerName, isUnassigned]);

  const changedCount = useMemo(() => {
    return chunks.filter((chunk) => {
      const current = chunkSpeakerMap[chunk.chunkId];
      if (isUnassigned) return !!current;
      return current !== undefined && current !== speakerName;
    }).length;
  }, [chunkSpeakerMap, chunks, speakerName, isUnassigned]);

  const toggleChunk = (chunkId: string) => {
    setSelectedChunks((prev) => {
      const next = new Set(prev);
      if (next.has(chunkId)) {
        next.delete(chunkId);
      } else {
        next.add(chunkId);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelectedChunks(new Set(chunks.map((c) => c.chunkId)));
  };

  const selectNone = () => {
    setSelectedChunks(new Set());
  };

  const handleRowSpeakerChange = (chunkId: string, value: string) => {
    if (value === "__new__") {
      setNewRowSpeakerNames((prev) => ({ ...prev, [chunkId]: "" }));
      return;
    }
    setNewRowSpeakerNames((prev) => {
      const next = { ...prev };
      delete next[chunkId];
      return next;
    });
    if (!isUnassigned && value === speakerName) {
      setChunkSpeakerMap((prev) => {
        const next = { ...prev };
        delete next[chunkId];
        return next;
      });
    } else {
      setChunkSpeakerMap((prev) => ({ ...prev, [chunkId]: value }));
    }
  };

  const confirmNewRowSpeaker = (chunkId: string) => {
    const name = (newRowSpeakerNames[chunkId] || "").trim();
    if (!isValidSpeakerName(name)) return;
    if (!customSpeakers.includes(name) && !allSpeakers.includes(name)) {
      setCustomSpeakers((prev) => [...prev, name]);
    }
    setChunkSpeakerMap((prev) => ({ ...prev, [chunkId]: name }));
    setNewRowSpeakerNames((prev) => {
      const next = { ...prev };
      delete next[chunkId];
      return next;
    });
  };

  const reassignSelected = () => {
    let targetSpeaker = bulkTarget;
    if (bulkTarget === "__new__") {
      targetSpeaker = newBulkSpeakerName.trim();
      if (!isValidSpeakerName(targetSpeaker)) return;
      if (!customSpeakers.includes(targetSpeaker) && !allSpeakers.includes(targetSpeaker)) {
        setCustomSpeakers((prev) => [...prev, targetSpeaker]);
      }
      setNewBulkSpeakerName("");
      setBulkTarget("__placeholder__");
    }
    if (!targetSpeaker || targetSpeaker === "__placeholder__") return;

    setChunkSpeakerMap((prev) => {
      const next = { ...prev };
      for (const chunkId of selectedChunks) {
        if (!isUnassigned && targetSpeaker === speakerName) {
          delete next[chunkId];
        } else {
          next[chunkId] = targetSpeaker;
        }
      }
      return next;
    });
    setNewRowSpeakerNames((prev) => {
      const next = { ...prev };
      for (const chunkId of selectedChunks) {
        delete next[chunkId];
      }
      return next;
    });
  };

  const applyMutation = useMutation({
    mutationFn: async () => {
      const updates = chunks
        .filter((chunk) => {
          const current = chunkSpeakerMap[chunk.chunkId];
          if (isUnassigned) return !!current;
          return current !== undefined && current !== speakerName;
        })
        .map((chunk) => ({
          chunkId: chunk.chunkId,
          speakerOverride: chunkSpeakerMap[chunk.chunkId],
        }));

      if (updates.length === 0) throw new Error("No changes to apply");

      const res = await apiRequest("POST", `/api/projects/${project.id}/chunks/batch-update`, {
        updates,
      });
      return res.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Speaker assignments updated",
        description: `${data.updatedChunks} chunk(s) reassigned successfully.`,
      });
      onOpenChange(false);
      setChunkSpeakerMap({});
      setSelectedChunks(new Set());
      setCustomSpeakers([]);
      onMergeComplete();
    },
    onError: (error: Error) => {
      toast({ title: "Update failed", description: error.message, variant: "destructive" });
    },
  });

  const dialogTitle = isUnassigned ? "Unassigned Dialogue" : `Speaker: ${speakerName}`;
  const dialogDesc = isUnassigned
    ? `${chunks.length} dialogue chunk${chunks.length !== 1 ? "s" : ""} without a speaker assignment. Assign speakers individually or in bulk.`
    : `${chunks.length} chunk${chunks.length !== 1 ? "s" : ""} attributed to this speaker. Reassign individually or select multiple to reassign in bulk.`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2" data-testid="text-speaker-dialog-title">
            {isUnassigned ? (
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
            ) : (
              <Users className="h-5 w-5 text-primary" />
            )}
            {dialogTitle}
          </DialogTitle>
          <DialogDescription>{dialogDesc}</DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2 text-sm">
          <Button variant="outline" size="sm" onClick={selectAll} data-testid="button-select-all">
            <SquareCheck className="h-3.5 w-3.5 mr-1" />
            Select All
          </Button>
          <Button variant="outline" size="sm" onClick={selectNone} data-testid="button-select-none">
            <Square className="h-3.5 w-3.5 mr-1" />
            Select None
          </Button>
          <span className="text-muted-foreground ml-auto">
            {selectedChunks.size} selected
          </span>
        </div>

        {selectedChunks.size > 0 && (
          <div className="flex items-center gap-2 p-2 rounded-lg bg-muted/50 border">
            <Label className="text-sm whitespace-nowrap">Reassign selected to:</Label>
            <Select value={bulkTarget} onValueChange={setBulkTarget}>
              <SelectTrigger className="w-[200px]" data-testid="select-bulk-target">
                <SelectValue placeholder="Select speaker..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__placeholder__" disabled>Select speaker...</SelectItem>
                {allAvailableSpeakers.map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
                <SelectItem value="__new__">+ New speaker...</SelectItem>
              </SelectContent>
            </Select>
            {bulkTarget === "__new__" && (
              <Input
                value={newBulkSpeakerName}
                onChange={(e) => setNewBulkSpeakerName(e.target.value)}
                placeholder="Speaker name"
                className="w-[160px]"
                data-testid="input-new-bulk-speaker"
                onKeyDown={(e) => { if (e.key === "Enter") reassignSelected(); }}
              />
            )}
            <Button
              size="sm"
              onClick={reassignSelected}
              disabled={bulkTarget === "__placeholder__" || (bulkTarget === "__new__" && !newBulkSpeakerName.trim())}
              data-testid="button-reassign-selected"
            >
              Reassign Selected
            </Button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto space-y-2 pr-1" data-testid="speaker-chunks-list">
          {chunks.map((chunk, idx) => {
            const currentSpeaker = getSpeakerForChunk(chunk.chunkId);
            const isChanged = isUnassigned ? !!chunkSpeakerMap[chunk.chunkId] : (chunkSpeakerMap[chunk.chunkId] !== undefined && chunkSpeakerMap[chunk.chunkId] !== speakerName);
            const isNewRow = chunk.chunkId in newRowSpeakerNames;
            const isDialogue = chunk.segmentType === "dialogue";

            return (
              <div
                key={chunk.chunkId}
                className={`rounded-lg border p-3 space-y-1.5 ${isChanged ? "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-300 dark:border-yellow-700" : "bg-card"}`}
                data-testid={`speaker-chunk-${idx}`}
              >
                <div className="flex items-start gap-2">
                  <Checkbox
                    checked={selectedChunks.has(chunk.chunkId)}
                    onCheckedChange={() => toggleChunk(chunk.chunkId)}
                    className="mt-0.5"
                    data-testid={`checkbox-chunk-${idx}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                      <span>{chunk.chapterTitle}</span>
                      <span>·</span>
                      <span>Sec {chunk.sectionIndex + 1}</span>
                      <Badge variant="outline" className="text-xs">{chunk.segmentType}</Badge>
                      {chunk.emotion && (
                        <Badge variant="secondary" className="text-xs">{chunk.emotion}</Badge>
                      )}
                      {isChanged && (
                        <Badge className="text-xs bg-yellow-500 text-white">\u2192 {currentSpeaker}</Badge>
                      )}
                    </div>
                    <div className="text-sm leading-relaxed">
                      {chunk.contextBefore && (
                        <span className="text-muted-foreground/60">
                          {wrapInQuotes(chunk.contextBefore.text, chunk.contextBefore.isDialogue)}{" "}
                        </span>
                      )}
                      <span className="bg-primary/15 rounded px-0.5 font-medium">
                        {wrapInQuotes(chunk.text, isDialogue)}
                      </span>
                      {chunk.contextAfter && (
                        <span className="text-muted-foreground/60">
                          {" "}{wrapInQuotes(chunk.contextAfter.text, chunk.contextAfter.isDialogue)}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0 flex items-center gap-1">
                    {isNewRow ? (
                      <div className="flex items-center gap-1">
                        <Input
                          value={newRowSpeakerNames[chunk.chunkId] || ""}
                          onChange={(e) =>
                            setNewRowSpeakerNames((prev) => ({ ...prev, [chunk.chunkId]: e.target.value }))
                          }
                          placeholder="Name"
                          className="w-[120px] h-8 text-xs"
                          data-testid={`input-new-row-speaker-${idx}`}
                          onKeyDown={(e) => { if (e.key === "Enter") confirmNewRowSpeaker(chunk.chunkId); }}
                          autoFocus
                        />
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 w-8 p-0"
                          onClick={() => confirmNewRowSpeaker(chunk.chunkId)}
                          disabled={!(newRowSpeakerNames[chunk.chunkId] || "").trim()}
                          data-testid={`confirm-new-row-speaker-${idx}`}
                        >
                          <Check className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    ) : (
                      <Select
                        value={currentSpeaker || "__unset__"}
                        onValueChange={(val) => {
                          if (val === "__unset__") {
                            if (isUnassigned) {
                              setChunkSpeakerMap((prev) => {
                                const next = { ...prev };
                                delete next[chunk.chunkId];
                                return next;
                              });
                            }
                            return;
                          }
                          handleRowSpeakerChange(chunk.chunkId, val);
                        }}
                      >
                        <SelectTrigger className="w-[140px] h-8 text-xs" data-testid={`select-row-speaker-${idx}`}>
                          <SelectValue placeholder="Assign speaker..." />
                        </SelectTrigger>
                        <SelectContent>
                          {isUnassigned && (
                            <SelectItem value="__unset__">Unassigned</SelectItem>
                          )}
                          {allAvailableSpeakers.map((s) => (
                            <SelectItem key={s} value={s}>{s}</SelectItem>
                          ))}
                          <SelectItem value="__new__">+ New speaker...</SelectItem>
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {chunks.length === 0 && (
            <div className="text-center text-muted-foreground py-8">
              {isUnassigned
                ? "All dialogue chunks have speakers assigned."
                : "No chunks found for this speaker."}
            </div>
          )}
        </div>

        <Separator />

        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            {changedCount > 0
              ? `${changedCount} chunk${changedCount !== 1 ? "s" : ""} will be reassigned`
              : "No changes"}
          </span>
          <Button
            onClick={() => applyMutation.mutate()}
            disabled={!hasChanges || applyMutation.isPending}
            data-testid="button-apply-changes"
          >
            {applyMutation.isPending ? "Applying..." : "Apply Changes"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
