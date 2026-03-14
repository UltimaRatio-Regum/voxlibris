import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Layers, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { ProjectData, ProjectChunk } from "@shared/schema";

const CANONICAL_EMOTIONS = [
  "neutral", "happy", "sad", "angry", "fear", "disgust", "surprise",
  "excited", "calm", "anxious", "hopeful", "melancholy", "tender", "proud",
];

interface BulkOverridePanelProps {
  selectedChunks: ProjectChunk[];
  selectedChunkIds: Set<string>;
  project: ProjectData;
  onRefresh: () => void;
  onClearSelection: () => void;
}

export function BulkOverridePanel({
  selectedChunks,
  selectedChunkIds,
  project,
  onRefresh,
  onClearSelection,
}: BulkOverridePanelProps) {
  const { toast } = useToast();
  const [speakerOverride, setSpeakerOverride] = useState("__skip__");
  const [emotionOverride, setEmotionOverride] = useState("__skip__");
  const [segmentType, setSegmentType] = useState("__skip__");

  const allSpeakers = new Set<string>();
  (project.chapters || []).forEach((ch) =>
    (ch.sections || []).forEach((sec) =>
      (sec.chunks || []).forEach((c) => {
        if (c.speaker) allSpeakers.add(c.speaker);
      })
    )
  );

  const hasChanges = speakerOverride !== "__skip__" || emotionOverride !== "__skip__" || segmentType !== "__skip__";

  const bulkMutation = useMutation({
    mutationFn: async () => {
      const body: Record<string, any> = {
        chunkIds: Array.from(selectedChunkIds),
      };

      if (speakerOverride === "__narrator__") {
        body.segmentType = "narration";
        body.speakerOverride = "";
      } else if (speakerOverride === "__clear__") {
        body.speakerOverride = "";
      } else if (speakerOverride !== "__skip__") {
        body.speakerOverride = speakerOverride;
        body.segmentType = "dialogue";
      }

      if (segmentType !== "__skip__") {
        body.segmentType = segmentType;
      }

      if (emotionOverride === "__clear__") {
        body.emotionOverride = "";
      } else if (emotionOverride !== "__skip__") {
        body.emotionOverride = emotionOverride;
      }

      await apiRequest("POST", `/api/projects/${project.id}/chunks/bulk-update`, body);
    },
    onSuccess: () => {
      toast({ title: `Updated ${selectedChunkIds.size} chunks` });
      onRefresh();
      onClearSelection();
    },
    onError: (error: Error) => {
      toast({ title: "Failed to update chunks", description: error.message, variant: "destructive" });
    },
  });

  const narrationCount = selectedChunks.filter(c => c.segmentType === "narration").length;
  const dialogueCount = selectedChunks.filter(c => c.segmentType === "dialogue").length;

  const speakerCounts = new Map<string, number>();
  for (const c of selectedChunks) {
    const spk = c.speakerOverride || c.speaker || "Narrator";
    speakerCounts.set(spk, (speakerCounts.get(spk) || 0) + 1);
  }

  return (
    <div className="space-y-4" data-testid="bulk-override-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-bold" data-testid="text-bulk-title">Bulk Edit</h2>
          <Badge variant="secondary" data-testid="badge-selected-count">
            {selectedChunkIds.size} chunks selected
          </Badge>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClearSelection}
          data-testid="button-clear-selection"
        >
          <X className="h-4 w-4 mr-1" />
          Clear Selection
        </Button>
      </div>

      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        {narrationCount > 0 && <Badge variant="outline">{narrationCount} narration</Badge>}
        {dialogueCount > 0 && <Badge variant="outline">{dialogueCount} dialogue</Badge>}
        {Array.from(speakerCounts.entries()).map(([spk, count]) => (
          <Badge key={spk} variant="outline">{spk}: {count}</Badge>
        ))}
      </div>

      <Separator />

      <div className="grid gap-4">
        <div className="space-y-2">
          <Label>Speaker Override</Label>
          <Select value={speakerOverride} onValueChange={(val) => {
            setSpeakerOverride(val);
            if (val === "__narrator__") {
              setSegmentType("narration");
            } else if (val !== "__skip__" && val !== "__clear__") {
              setSegmentType("dialogue");
            } else {
              setSegmentType("__skip__");
            }
          }}>
            <SelectTrigger data-testid="select-bulk-speaker">
              <SelectValue placeholder="No change" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__skip__">No change</SelectItem>
              <SelectItem value="__clear__">Clear override</SelectItem>
              <SelectItem value="__narrator__">Narrator (narration)</SelectItem>
              {Array.from(allSpeakers).map((s) => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Segment Type Override</Label>
          <Select value={segmentType} onValueChange={setSegmentType}>
            <SelectTrigger data-testid="select-bulk-segment-type">
              <SelectValue placeholder="No change" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__skip__">No change</SelectItem>
              <SelectItem value="narration">Narration</SelectItem>
              <SelectItem value="dialogue">Dialogue</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>Emotion Override</Label>
          <Select value={emotionOverride} onValueChange={setEmotionOverride}>
            <SelectTrigger data-testid="select-bulk-emotion">
              <SelectValue placeholder="No change" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__skip__">No change</SelectItem>
              <SelectItem value="__clear__">Clear override</SelectItem>
              {CANONICAL_EMOTIONS.map((e) => (
                <SelectItem key={e} value={e}>{e}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          onClick={() => bulkMutation.mutate()}
          disabled={bulkMutation.isPending || !hasChanges}
          size="sm"
          data-testid="button-bulk-apply"
        >
          <Save className="h-4 w-4 mr-2" />
          {bulkMutation.isPending ? "Applying..." : `Apply to ${selectedChunkIds.size} Chunks`}
        </Button>
      </div>
    </div>
  );
}
