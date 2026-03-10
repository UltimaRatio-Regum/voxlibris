import { useState, useRef } from "react";
import { Play, Pause, Volume2, Clock, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ProjectAudioFile } from "@shared/schema";

interface ProjectAudioListProps {
  audioFiles: ProjectAudioFile[];
  projectId: string;
}

function AudioFileEntry({ audio, projectId }: { audio: ProjectAudioFile; projectId: string }) {
  const [isPlaying, setIsPlaying] = useState(false);
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

  const audioUrl = `/api/projects/${projectId}/audio/${audio.id}`;

  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border bg-card" data-testid={`audio-entry-${audio.id}`}>
      <Button
        variant="outline"
        size="sm"
        className="h-8 w-8 p-0 shrink-0"
        onClick={togglePlay}
        data-testid={`button-play-${audio.id}`}
      >
        {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
      </Button>

      <audio
        ref={audioRef}
        src={audioUrl}
        onEnded={() => setIsPlaying(false)}
        onPause={() => setIsPlaying(false)}
        onPlay={() => setIsPlaying(true)}
      />

      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {audio.durationSeconds && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {audio.durationSeconds.toFixed(1)}s
            </span>
          )}
          {audio.ttsEngine && (
            <span className="flex items-center gap-1">
              <Cpu className="h-3 w-3" />
              {audio.ttsEngine}
            </span>
          )}
          {audio.voiceId && (
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

export function ProjectAudioList({ audioFiles, projectId }: ProjectAudioListProps) {
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
        <AudioFileEntry key={audio.id} audio={audio} projectId={projectId} />
      ))}
    </div>
  );
}
