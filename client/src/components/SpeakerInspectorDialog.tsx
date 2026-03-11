import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Users, ArrowRight, MessageSquareQuote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
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
  const [mergeTarget, setMergeTarget] = useState("__existing__");
  const [newSpeakerName, setNewSpeakerName] = useState("");

  const chunks = getChunksForSpeaker(project, speakerName);
  const otherSpeakers = allSpeakers.filter((s) => s !== speakerName);

  const mergeMutation = useMutation({
    mutationFn: async () => {
      const toSpeaker = mergeTarget === "__new__" ? newSpeakerName.trim() : mergeTarget;
      if (!toSpeaker) throw new Error("Please specify a speaker name");
      if (toSpeaker === speakerName) throw new Error("Cannot merge a speaker into themselves");

      const res = await apiRequest("POST", `/api/projects/${project.id}/speakers/merge`, {
        fromSpeaker: speakerName,
        toSpeaker,
      });
      return res.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Speakers merged",
        description: `${data.updatedChunks} chunk(s) reassigned successfully.`,
      });
      onOpenChange(false);
      onMergeComplete();
    },
    onError: (error: Error) => {
      toast({ title: "Merge failed", description: error.message, variant: "destructive" });
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2" data-testid="text-speaker-dialog-title">
            <Users className="h-5 w-5 text-primary" />
            Speaker: {speakerName}
          </DialogTitle>
          <DialogDescription>
            {chunks.length} chunk{chunks.length !== 1 ? "s" : ""} attributed to this speaker
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-3 pr-1" data-testid="speaker-chunks-list">
          {chunks.map((chunk, idx) => (
            <div
              key={chunk.chunkId}
              className="rounded-lg border bg-card p-3 space-y-1"
              data-testid={`speaker-chunk-${idx}`}
            >
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>{chunk.chapterTitle}</span>
                <span>·</span>
                <span>Section {chunk.sectionIndex + 1}</span>
                <Badge variant="outline" className="text-xs">{chunk.segmentType}</Badge>
                {chunk.emotion && (
                  <Badge variant="secondary" className="text-xs">{chunk.emotion}</Badge>
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
          ))}

          {chunks.length === 0 && (
            <div className="text-center text-muted-foreground py-8">
              No chunks found for this speaker.
            </div>
          )}
        </div>

        <Separator />

        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="flex items-center gap-1.5">
              <ArrowRight className="h-4 w-4" />
              Reassign all chunks to another speaker
            </Label>
            <p className="text-xs text-muted-foreground">
              This will change the speaker on all {chunks.length} chunk(s) from "{speakerName}" to the selected speaker.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Select value={mergeTarget} onValueChange={setMergeTarget}>
              <SelectTrigger className="flex-1" data-testid="select-merge-target">
                <SelectValue placeholder="Select speaker..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__existing__" disabled>Select a speaker...</SelectItem>
                {otherSpeakers.map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
                <SelectItem value="__new__">+ New speaker name...</SelectItem>
              </SelectContent>
            </Select>

            {mergeTarget === "__new__" && (
              <Input
                value={newSpeakerName}
                onChange={(e) => setNewSpeakerName(e.target.value)}
                placeholder="Enter speaker name"
                className="flex-1"
                data-testid="input-new-speaker-name"
              />
            )}

            <Button
              onClick={() => mergeMutation.mutate()}
              disabled={
                mergeMutation.isPending ||
                mergeTarget === "__existing__" ||
                (mergeTarget === "__new__" && !newSpeakerName.trim())
              }
              data-testid="button-merge-speakers"
            >
              <MessageSquareQuote className="h-4 w-4 mr-1" />
              {mergeMutation.isPending ? "Merging..." : "Merge"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
