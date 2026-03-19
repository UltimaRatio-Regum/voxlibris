import { useState } from "react";
import { Archive, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import type { ProjectData } from "@shared/schema";

interface BackupProjectDialogProps {
  project: ProjectData;
}

export function BackupProjectDialog({ project }: BackupProjectDialogProps) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [includeAudio, setIncludeAudio] = useState(false);
  const [includeVoices, setIncludeVoices] = useState(false);
  const [includeSource, setIncludeSource] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleBackup = async () => {
    setIsLoading(true);
    const params = new URLSearchParams();
    if (includeAudio) params.set("include_audio", "true");
    if (includeVoices) params.set("include_voices", "true");
    if (includeSource) params.set("include_source", "true");

    try {
      const response = await fetch(
        `/api/projects/${project.id}/backup?${params}`,
        { credentials: "include" }
      );
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Backup failed" }));
        throw new Error(err.detail || "Backup failed");
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = response.headers.get("content-disposition");
      const match = disposition?.match(/filename="?(.+?)"?$/);
      const isZip = blob.type === "application/zip";
      const safeName = project.title.replace(/[^\w\s\-]/g, "").trim().slice(0, 50);
      a.download = match?.[1] || `${safeName}_backup.${isZip ? "zip" : "json"}`;
      a.click();
      URL.revokeObjectURL(url);

      toast({ title: "Backup created", description: `Downloaded as ${a.download}` });
      setOpen(false);
    } catch (err: any) {
      toast({ title: "Backup failed", description: err.message, variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };

  const willProduceZip = (includeAudio || includeVoices || includeSource);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="w-full" data-testid="button-backup-project">
          <Archive className="h-3.5 w-3.5 mr-2" />
          Backup Project
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Backup Project</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <p className="text-sm text-muted-foreground">
            Creates a portable backup of all project data including chapter text, chunk assignments,
            speaker configs, and overrides. Choose what additional content to include:
          </p>

          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <Checkbox
                id="backup-audio"
                checked={includeAudio}
                onCheckedChange={(v) => setIncludeAudio(v === true)}
                data-testid="checkbox-backup-audio"
              />
              <div className="space-y-0.5">
                <Label htmlFor="backup-audio" className="text-sm font-medium cursor-pointer">
                  Include generated audio chunks
                </Label>
                <p className="text-xs text-muted-foreground">
                  Embeds all chunk-level MP3 files in the backup. Can be large for long books.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <Checkbox
                id="backup-voices"
                checked={includeVoices}
                onCheckedChange={(v) => setIncludeVoices(v === true)}
                data-testid="checkbox-backup-voices"
              />
              <div className="space-y-0.5">
                <Label htmlFor="backup-voices" className="text-sm font-medium cursor-pointer">
                  Include custom voice samples
                </Label>
                <p className="text-xs text-muted-foreground">
                  Embeds the audio files for any custom (uploaded) voices used by this project.
                  Built-in voices are identified by ID and do not need to be included.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <Checkbox
                id="backup-source"
                checked={includeSource}
                onCheckedChange={(v) => setIncludeSource(v === true)}
                disabled={!project.hasSourceFile}
                data-testid="checkbox-backup-source"
              />
              <div className="space-y-0.5">
                <Label
                  htmlFor="backup-source"
                  className={`text-sm font-medium cursor-pointer ${!project.hasSourceFile ? "text-muted-foreground" : ""}`}
                >
                  Include source file
                  {!project.hasSourceFile && (
                    <span className="ml-2 text-xs font-normal text-muted-foreground">(not available — uploaded before this feature was added)</span>
                  )}
                </Label>
                <p className="text-xs text-muted-foreground">
                  Includes the original {project.sourceType === "epub" ? "EPUB" : "text"} file
                  {project.sourceFilename ? ` (${project.sourceFilename})` : ""} used to create this project.
                </p>
              </div>
            </div>
          </div>

          <Separator />

          <p className="text-xs text-muted-foreground">
            {willProduceZip
              ? "Output will be a ZIP file containing project.json plus any selected binary content."
              : "Output will be a JSON file containing all project data."}
          </p>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} disabled={isLoading}>
              Cancel
            </Button>
            <Button onClick={handleBackup} disabled={isLoading} data-testid="button-backup-confirm">
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Creating backup...
                </>
              ) : (
                <>
                  <Archive className="h-4 w-4 mr-2" />
                  Create Backup
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
