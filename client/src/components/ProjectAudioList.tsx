import { useState, useRef } from "react";
import { Play, Pause, Volume2, Clock, Cpu, FileAudio, Download, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { ProjectAudioFile } from "@shared/schema";

interface ProjectAudioListProps {
  audioFiles: ProjectAudioFile[];
  projectId: string;
  onDelete?: () => void;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins < 60) return `${mins}m ${secs}s`;
  const hrs = Math.floor(mins / 60);
  const remainMins = mins % 60;
  return `${hrs}h ${remainMins}m`;
}

function AudioFileEntry({ audio, projectId, onDelete }: { audio: ProjectAudioFile; projectId: string; onDelete?: () => void }) {
  const { toast } = useToast();
  const [isPlaying, setIsPlaying] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      const response = await fetch(`/api/projects/${projectId}/audio/${audio.id}`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const label = audio.label?.replace(/[^a-zA-Z0-9_\- ]/g, "") || "audio";
      a.download = `${label}.wav`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast({ title: "Download failed", description: "Could not download audio segment", variant: "destructive" });
    } finally {
      setIsDownloading(false);
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await apiRequest("DELETE", `/api/projects/${projectId}/audio/${audio.id}`);
      toast({ title: "Audio file deleted" });
      onDelete?.();
    } catch {
      toast({ title: "Delete failed", variant: "destructive" });
    } finally {
      setIsDeleting(false);
    }
  };

  const audioUrl = `/api/projects/${projectId}/audio/${audio.id}`;
  const isCombined = audio.scopeType !== "chunk";

  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border bg-card" data-testid={`audio-entry-${audio.id}`}>
      <div className="flex items-center gap-1 shrink-0">
        <Button
          variant="outline"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={togglePlay}
          data-testid={`button-play-${audio.id}`}
        >
          {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={handleDownload}
          disabled={isDownloading}
          data-testid={`button-download-segment-${audio.id}`}
        >
          {isDownloading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Download className="h-3.5 w-3.5" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
          onClick={handleDelete}
          disabled={isDeleting}
          data-testid={`button-delete-audio-${audio.id}`}
        >
          {isDeleting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Trash2 className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>

      <audio
        ref={audioRef}
        src={audioUrl}
        onEnded={() => setIsPlaying(false)}
        onPause={() => setIsPlaying(false)}
        onPlay={() => setIsPlaying(true)}
      />

      <div className="flex-1 min-w-0 space-y-1">
        {audio.label && (
          <div className="flex items-center gap-1.5 text-sm font-medium truncate" data-testid={`text-audio-label-${audio.id}`}>
            {isCombined && <FileAudio className="h-3.5 w-3.5 text-primary shrink-0" />}
            <span className="truncate">{audio.label}</span>
          </div>
        )}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {audio.durationSeconds && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDuration(audio.durationSeconds)}
            </span>
          )}
          {audio.ttsEngine && (
            <span className="flex items-center gap-1">
              <Cpu className="h-3 w-3" />
              {audio.ttsEngine}
            </span>
          )}
          {!isCombined && audio.voiceId && (
            <span className="truncate">{audio.voiceId}</span>
          )}
        </div>
        {audio.createdAt && (
          <div className="text-xs text-muted-foreground">
            {new Date(audio.createdAt).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}

export function ProjectAudioList({ audioFiles, projectId, onDelete }: ProjectAudioListProps) {
  if (audioFiles.length === 0) {
    return (
      <div className="text-center py-6 text-sm text-muted-foreground" data-testid="text-no-audio">
        <Volume2 className="h-8 w-8 mx-auto mb-2 opacity-50" />
        <p>No audio generated yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="audio-files-list">
      {audioFiles.map((audio) => (
        <AudioFileEntry key={audio.id} audio={audio} projectId={projectId} onDelete={onDelete} />
      ))}
    </div>
  );
}
