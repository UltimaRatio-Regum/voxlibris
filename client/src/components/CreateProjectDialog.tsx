import { useState, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Upload, FileText, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import type { ProjectData } from "@shared/schema";

interface CreateProjectDialogProps {
  onProjectCreated: (project: ProjectData) => void;
}

export function CreateProjectDialog({ onProjectCreated }: CreateProjectDialogProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [inputMode, setInputMode] = useState<"text" | "epub">("text");
  const [epubFile, setEpubFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const createMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData();
      formData.append("title", title);
      if (inputMode === "text") {
        formData.append("text", text);
      } else if (epubFile) {
        formData.append("file", epubFile);
      }

      const res = await fetch("/api/projects", {
        method: "POST",
        body: formData,
        credentials: "include",
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || res.statusText);
      }
      return res.json() as Promise<ProjectData>;
    },
    onSuccess: async (project) => {
      try {
        const segRes = await fetch(`/api/projects/${project.id}/segment`, {
          method: "POST",
          credentials: "include",
        });
        if (!segRes.ok) {
          toast({ title: "Project created", description: "Segmentation failed to start. You can retry from the project editor.", variant: "destructive" });
        } else {
          toast({ title: "Project created", description: "Segmentation started in the background." });
        }
      } catch {
        toast({ title: "Project created", description: "Segmentation failed to start.", variant: "destructive" });
      }
      queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
      setOpen(false);
      setTitle("");
      setText("");
      setEpubFile(null);
      onProjectCreated(project);
    },
    onError: (error: Error) => {
      toast({ title: "Failed to create project", description: error.message, variant: "destructive" });
    },
  });

  const canSubmit = title.trim().length > 0 && (inputMode === "text" ? text.trim().length > 0 : epubFile !== null);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button data-testid="button-new-project">
          <Plus className="h-4 w-4 mr-2" />
          New Project
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>Create New Project</DialogTitle>
          <DialogDescription>
            Create a new audiobook project from text or an EPUB file.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="project-title">Project Title</Label>
            <Input
              id="project-title"
              data-testid="input-project-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="My Audiobook"
            />
          </div>

          <div className="flex gap-2">
            <Button
              variant={inputMode === "text" ? "default" : "outline"}
              size="sm"
              onClick={() => setInputMode("text")}
              data-testid="button-input-text"
            >
              <FileText className="h-4 w-4 mr-1" />
              Paste Text
            </Button>
            <Button
              variant={inputMode === "epub" ? "default" : "outline"}
              size="sm"
              onClick={() => setInputMode("epub")}
              data-testid="button-input-epub"
            >
              <Upload className="h-4 w-4 mr-1" />
              Upload EPUB
            </Button>
          </div>

          {inputMode === "text" ? (
            <div className="space-y-2">
              <Label htmlFor="project-text">Text Content</Label>
              <Textarea
                id="project-text"
                data-testid="input-project-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste your book text here..."
                rows={10}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">
                {text.split(/\s+/).filter(Boolean).length} words
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <Label>EPUB File</Label>
              <div
                className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary/50 transition-colors"
                onClick={() => fileInputRef.current?.click()}
                data-testid="dropzone-epub"
              >
                {epubFile ? (
                  <div className="flex items-center justify-center gap-2">
                    <FileText className="h-5 w-5 text-primary" />
                    <span className="text-sm font-medium">{epubFile.name}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEpubFile(null);
                      }}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                ) : (
                  <div>
                    <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">Click to select an EPUB file</p>
                  </div>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".epub"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) setEpubFile(file);
                }}
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} data-testid="button-cancel-project">
            Cancel
          </Button>
          <Button
            onClick={() => createMutation.mutate()}
            disabled={!canSubmit || createMutation.isPending}
            data-testid="button-create-project"
          >
            {createMutation.isPending ? "Creating..." : "Create & Segment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
