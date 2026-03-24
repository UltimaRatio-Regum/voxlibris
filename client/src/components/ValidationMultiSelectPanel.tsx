import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Wand2, Loader2, Flag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { ProjectData } from "@shared/schema";

interface ValidationMultiSelectPanelProps {
  selectedIds: Set<string>;
  project: ProjectData;
  onRefresh: () => void;
  onClearSelection: () => void;
}

export function ValidationMultiSelectPanel({ selectedIds, project, onRefresh, onClearSelection }: ValidationMultiSelectPanelProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const ids = Array.from(selectedIds);
  const count = ids.length;

  const markAllGoodMutation = useMutation({
    mutationFn: async () => {
      await Promise.all(
        ids.map((chunkId) =>
          apiRequest("PATCH", `/api/projects/${project.id}/validation/chunks/${chunkId}`, { isFlagged: false }),
        ),
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id, "validation/results"] });
      onRefresh();
      onClearSelection();
      toast({ title: "Marked as good", description: `${count} chunk${count !== 1 ? "s" : ""} marked as good.` });
    },
    onError: (e: Error) => {
      toast({ title: "Update failed", description: e.message, variant: "destructive" });
    },
  });

  const regenerateAllMutation = useMutation({
    mutationFn: async () => {
      for (const chunkId of ids) {
        await apiRequest("POST", `/api/projects/${project.id}/generate`, {
          scopeType: "chunk",
          scopeId: chunkId,
          onlyMissing: false,
        });
        await apiRequest("PATCH", `/api/projects/${project.id}/validation/chunks/${chunkId}`, { isRegenerated: true });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id, "validation/results"] });
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
      onRefresh();
      onClearSelection();
      toast({ title: "Regeneration queued", description: `${count} chunk${count !== 1 ? "s" : ""} submitted for re-generation.` });
    },
    onError: (e: Error) => {
      toast({ title: "Regeneration failed", description: e.message, variant: "destructive" });
    },
  });

  const isPending = markAllGoodMutation.isPending || regenerateAllMutation.isPending;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Flag className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-base font-semibold">{count} flagged chunk{count !== 1 ? "s" : ""} selected</h2>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => markAllGoodMutation.mutate()}
          disabled={isPending}
        >
          {markAllGoodMutation.isPending
            ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Marking…</>
            : <><CheckCircle2 className="h-4 w-4 mr-2 text-green-500" />Mark All as Good</>}
        </Button>
        <Button
          variant="destructive"
          onClick={() => regenerateAllMutation.mutate()}
          disabled={isPending}
        >
          {regenerateAllMutation.isPending
            ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Queuing…</>
            : <><Wand2 className="h-4 w-4 mr-2" />Regenerate All</>}
        </Button>
      </div>
    </div>
  );
}
