import { useState, useMemo, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Users, Check, CheckSquare, Square, SquareCheck } from "lucide-react";
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

interface ChunkWithContext {
  chunkId: string;
  chapterTitle: string;
  sectionIndex: number;
  chunkIndex: number;
  text: string;
  contextBefore: string;
  contextAfter: string;
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

function getChunksForSpeaker(project: ProjectData, speakerName: string): ChunkWithContext[] {
  const results: ChunkWithContext[] = [];

  for (const chapter of project.chapters || []) {
    for (const section of chapter.sections || []) {
      const chunks = section.chunks || [];
      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        const effectiveSpeaker = chunk.speakerOverride || chunk.speaker;
        if (effectiveSpeaker !== speakerName) continue;

        const contextBefore = chunks
          .slice(Math.max(0, i - 1), i)
          .map((c) => c.text)
          .join(" ");
        const contextAfter = chunks
          .slice(i + 1, i + 2)
          .map((c) => c.text)
          .join(" ");

        results.push({
          chunkId: chunk.id,
          chapterTitle: chapter.title || `Chapter ${chapter.chapterIndex + 1}`,
          sectionIndex: section.sectionIndex,
          chunkIndex: i,
          text: chunk.text,
          contextBefore: contextBefore.length > 150 ? "..." + contextBefore.slice(-150) : contextBefore,
          contextAfter: contextAfter.length > 150 ? contextAfter.slice(0, 150) + "..." : contextAfter,
          segmentType: chunk.segmentType || "narration",
          emotion: chunk.emotion || null,
          originalSpeaker: speakerName,
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

  const RESERVED_NAMES = ["__new__", "__placeholder__", "__existing__"];

  const isValidSpeakerName = (name: string): boolean => {
    const trimmed = name.trim();
    return trimmed.length > 0 && !RESERVED_NAMES.includes(trimmed);
  };

  const allAvailableSpeakers = useMemo(() => {
    const combined = new Set([...allSpeakers, ...customSpeakers]);
    return Array.from(combined).sort();
  }, [allSpeakers, customSpeakers]);

  const getSpeakerForChunk = (chunkId: string) => {
    return chunkSpeakerMap[chunkId] || speakerName;
  };

  const hasChanges = useMemo(() => {
    return chunks.some((chunk) => {
      const current = getSpeakerForChunk(chunk.chunkId);
      return current !== speakerName;
    });
  }, [chunkSpeakerMap, chunks, speakerName]);

  const changedCount = useMemo(() => {
    return chunks.filter((chunk) => getSpeakerForChunk(chunk.chunkId) !== speakerName).length;
  }, [chunkSpeakerMap, chunks, speakerName]);

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
    if (value === speakerName) {
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

    const updates: Record<string, string> = {};
    for (const chunkId of selectedChunks) {
      if (targetSpeaker === speakerName) {
        updates[chunkId] = speakerName;
      } else {
        updates[chunkId] = targetSpeaker;
      }
    }
    setChunkSpeakerMap((prev) => {
      const next = { ...prev };
      for (const [chunkId, speaker] of Object.entries(updates)) {
        if (speaker === speakerName) {
          delete next[chunkId];
        } else {
          next[chunkId] = speaker;
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
        .filter((chunk) => getSpeakerForChunk(chunk.chunkId) !== speakerName)
        .map((chunk) => ({
          chunkId: chunk.chunkId,
          speakerOverride: getSpeakerForChunk(chunk.chunkId),
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2" data-testid="text-speaker-dialog-title">
            <Users className="h-5 w-5 text-primary" />
            Speaker: {speakerName}
          </DialogTitle>
          <DialogDescription>
            {chunks.length} chunk{chunks.length !== 1 ? "s" : ""} attributed to this speaker.
            Reassign individually or select multiple to reassign in bulk.
          </DialogDescription>
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
            const isChanged = currentSpeaker !== speakerName;
            const isNewRow = chunk.chunkId in newRowSpeakerNames;

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
                        <Badge className="text-xs bg-yellow-500 text-white">→ {currentSpeaker}</Badge>
                      )}
                    </div>
                    <div className="text-sm leading-relaxed">
                      {chunk.contextBefore && (
                        <span className="text-muted-foreground/60">{chunk.contextBefore} </span>
                      )}
                      <span className="bg-primary/15 rounded px-0.5 font-medium">{chunk.text}</span>
                      {chunk.contextAfter && (
                        <span className="text-muted-foreground/60"> {chunk.contextAfter}</span>
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
                        value={currentSpeaker}
                        onValueChange={(val) => handleRowSpeakerChange(chunk.chunkId, val)}
                      >
                        <SelectTrigger className="w-[140px] h-8 text-xs" data-testid={`select-row-speaker-${idx}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
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
              No chunks found for this speaker.
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
