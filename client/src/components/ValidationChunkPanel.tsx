import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Play, Pause, CheckCircle2, Wand2, Loader2, Flag, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { ProjectData } from "@shared/schema";

interface ValidationResult {
  chunkId: string;
  chunkText: string;
  sttText: string | null;
  processedSourceText: string | null;
  processedSttText: string | null;
  algorithmScores: Record<string, number>;
  combinedScore: number | null;
  isFlagged: boolean;
  isRegenerated: boolean;
}

interface ValidationChunkPanelProps {
  chunkId: string;
  project: ProjectData;
  onRefresh: () => void;
}

export function ValidationChunkPanel({ chunkId, project, onRefresh }: ValidationChunkPanelProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);

  const { data: resultsData, isLoading } = useQuery<{
    results: ValidationResult[];
  }>({
    queryKey: ["/api/projects", project.id, "validation/results"],
  });

  const result = resultsData?.results.find((r) => r.chunkId === chunkId);

  const audioUrl = `/api/projects/${project.id}/chunks/${chunkId}/audio`;

  const patchMutation = useMutation({
    mutationFn: async (patch: { isFlagged?: boolean; isRegenerated?: boolean }) => {
      const res = await apiRequest(
        "PATCH",
        `/api/projects/${project.id}/validation/chunks/${chunkId}`,
        patch,
      );
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id, "validation/results"] });
      onRefresh();
    },
    onError: (e: Error) => {
      toast({ title: "Update failed", description: e.message, variant: "destructive" });
    },
  });

  const regenMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/projects/${project.id}/generate`, {
        scopeType: "chunk",
        scopeId: chunkId,
        onlyMissing: false,
      });
      return res.json();
    },
    onSuccess: () => {
      // Mark as regenerated in validation results
      patchMutation.mutate({ isRegenerated: true });
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
      toast({ title: "Regeneration queued", description: "Chunk submitted for re-generation." });
    },
    onError: (e: Error) => {
      toast({ title: "Regeneration failed", description: e.message, variant: "destructive" });
    },
  });

  const togglePlay = () => {
    if (playing && audioRef.current) {
      audioRef.current.pause();
      setPlaying(false);
      return;
    }
    if (audioRef.current) {
      audioRef.current.pause();
    }
    const audio = new Audio(audioUrl);
    audioRef.current = audio;
    audio.onended = () => setPlaying(false);
    audio.onerror = () => { setPlaying(false); toast({ title: "No audio available", variant: "destructive" }); };
    audio.play().then(() => setPlaying(true)).catch(() => {
      setPlaying(false);
      toast({ title: "No audio available", description: "This chunk has not been generated yet.", variant: "destructive" });
    });
  };

  if (isLoading) {
    return <div className="py-8 text-center text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Loading…</div>;
  }

  if (!result) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground py-8">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Validation result not found for this chunk.
      </div>
    );
  }

  const scoreEntries = Object.entries(result.algorithmScores);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Flag className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-base font-semibold">Flagged Chunk</h2>
        </div>
        <div className="flex items-center gap-2">
          {result.combinedScore !== null && (
            <Badge variant={result.combinedScore < 0.6 ? "destructive" : "secondary"}>
              {(result.combinedScore * 100).toFixed(1)}% similar
            </Badge>
          )}
          {result.isRegenerated && (
            <Badge variant="outline">Regenerated</Badge>
          )}
        </div>
      </div>

      {/* Source text */}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Source Text</p>
        <div className="rounded-md border bg-muted/40 p-3 text-sm leading-relaxed">
          {result.chunkText}
        </div>
      </div>

      {/* STT text */}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          STT Transcript
        </p>
        <div className="rounded-md border bg-muted/40 p-3 text-sm leading-relaxed">
          {result.sttText ? result.sttText : <span className="text-muted-foreground italic">No transcript</span>}
        </div>
      </div>

      {/* Processed texts (used for comparison) */}
      {(result.processedSourceText != null || result.processedSttText != null) && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Processed (used for comparison)
          </p>
          {result.processedSourceText != null && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Source</p>
              <div className="rounded-md border bg-muted/20 p-3 text-xs font-mono leading-relaxed break-all">
                {result.processedSourceText || <span className="italic">(empty)</span>}
              </div>
            </div>
          )}
          {result.processedSttText != null && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">STT Transcript</p>
              <div className="rounded-md border bg-muted/20 p-3 text-xs font-mono leading-relaxed break-all">
                {result.processedSttText || <span className="italic">(empty)</span>}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Per-algorithm scores */}
      {scoreEntries.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Algorithm Scores</p>
          <div className="grid grid-cols-2 gap-2">
            {scoreEntries.map(([algo, score]) => (
              <div key={algo} className="flex items-center justify-between rounded-md border px-3 py-1.5 text-sm">
                <span className="text-muted-foreground">{algo.replace(/_/g, " ")}</span>
                <span className={score < 0.7 ? "text-destructive font-medium" : "font-medium"}>
                  {(score * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Audio playback */}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Generated Audio</p>
        <Button variant="outline" size="sm" onClick={togglePlay}>
          {playing ? <><Pause className="h-4 w-4 mr-2" />Pause</> : <><Play className="h-4 w-4 mr-2" />Play</>}
        </Button>
      </div>

      <Separator />

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => patchMutation.mutate({ isFlagged: false })}
          disabled={patchMutation.isPending || !result.isFlagged}
        >
          <CheckCircle2 className="h-4 w-4 mr-2 text-green-500" />
          Mark as Good
        </Button>
        <Button
          variant="destructive"
          onClick={() => regenMutation.mutate()}
          disabled={regenMutation.isPending || result.isRegenerated}
        >
          {regenMutation.isPending
            ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Queuing…</>
            : <><Wand2 className="h-4 w-4 mr-2" />Regenerate Chunk</>}
        </Button>
      </div>
    </div>
  );
}
