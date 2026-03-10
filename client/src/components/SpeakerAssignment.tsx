import { useState, useRef, useCallback } from "react";
import { Users, Mic, Volume2, Library, Globe, Plus, Upload, Server } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { isVoiceCloningEngine } from "@/lib/tts-engines";
import type { RegisteredEngine } from "@/components/SettingsPanel";
import type { VoiceSample, SpeakerConfig, LibraryVoice, EdgeVoice, TTSEngine } from "@shared/schema";

interface SpeakerAssignmentProps {
  speakers: string[];
  voiceSamples: VoiceSample[];
  libraryVoices: LibraryVoice[];
  edgeVoices: EdgeVoice[];
  ttsEngine: TTSEngine;
  registeredEngines?: RegisteredEngine[];
  speakerConfigs: Record<string, SpeakerConfig>;
  narratorVoiceId: string | null;
  onUpdateSpeakerConfig: (speaker: string, config: Partial<SpeakerConfig>) => void;
  onUpdateNarratorVoice: (voiceId: string | null) => void;
  onVoiceUploaded?: (voiceId: string) => void;
}

const UPLOAD_NEW_VALUE = "__upload_new__";

export function SpeakerAssignment({
  speakers,
  voiceSamples,
  libraryVoices,
  edgeVoices,
  ttsEngine,
  registeredEngines = [],
  speakerConfigs,
  narratorVoiceId,
  onUpdateSpeakerConfig,
  onUpdateNarratorVoice,
  onVoiceUploaded,
}: SpeakerAssignmentProps) {
  const { toast } = useToast();
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [uploadTarget, setUploadTarget] = useState<{ type: "narrator" | "speaker"; speaker?: string } | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentRegisteredEngine = registeredEngines.find(e => e.engine_id === ttsEngine);
  const registeredBuiltinVoices = currentRegisteredEngine?.builtin_voices ?? [];

  const handleVoiceChange = useCallback((value: string, target: { type: "narrator" | "speaker"; speaker?: string }) => {
    if (value === UPLOAD_NEW_VALUE) {
      setUploadTarget(target);
      setUploadDialogOpen(true);
      return;
    }
    if (target.type === "narrator") {
      onUpdateNarratorVoice(value === "none" ? null : value);
    } else if (target.speaker) {
      onUpdateSpeakerConfig(target.speaker, { voiceSampleId: value === "none" ? null : value });
    }
  }, [onUpdateNarratorVoice, onUpdateSpeakerConfig]);

  const handleUploadSubmit = useCallback(async () => {
    if (!uploadFile || !uploadName.trim()) return;
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("name", uploadName.trim());
      formData.append("file", uploadFile);
      const res = await fetch("/api/voices/upload", { method: "POST", body: formData });
      if (!res.ok) throw new Error("Upload failed");
      const data = await res.json();
      const newVoiceId = data.id || data.voice_id;
      if (!newVoiceId) {
        toast({ title: "Upload error", description: "Voice was uploaded but no ID was returned.", variant: "destructive" });
        return;
      }
      if (uploadTarget) {
        if (uploadTarget.type === "narrator") {
          onUpdateNarratorVoice(newVoiceId);
        } else if (uploadTarget.speaker) {
          onUpdateSpeakerConfig(uploadTarget.speaker, { voiceSampleId: newVoiceId });
        }
      }
      onVoiceUploaded?.(newVoiceId);
      toast({ title: "Voice uploaded", description: "Voice sample added and selected." });
      setUploadDialogOpen(false);
      setUploadName("");
      setUploadFile(null);
      setUploadTarget(null);
    } catch {
      toast({ title: "Upload failed", description: "Could not upload the voice sample.", variant: "destructive" });
    } finally {
      setIsUploading(false);
    }
  }, [uploadFile, uploadName, uploadTarget, onUpdateNarratorVoice, onUpdateSpeakerConfig, onVoiceUploaded, toast]);

  const renderVoiceOptions = () => {
    const showEdgeVoices = ttsEngine === "edge-tts" && edgeVoices.length > 0;
    const supportsCloning = isVoiceCloningEngine(ttsEngine) || (currentRegisteredEngine?.supports_voice_cloning ?? false);
    const showLibraryVoices = supportsCloning && libraryVoices.length > 0;
    const showRegisteredVoices = registeredBuiltinVoices.length > 0;
    
    return (
      <>
        <SelectItem value="none">Default (No cloning)</SelectItem>
        
        {showEdgeVoices && (
          <SelectGroup>
            <SelectLabel className="flex items-center gap-2">
              <Globe className="h-3 w-3" />
              Azure Neural Voices
            </SelectLabel>
            {edgeVoices.slice(0, 20).map((voice) => (
              <SelectItem key={voice.id} value={`edge:${voice.id}`}>
                <div className="flex items-center gap-2">
                  <Globe className="h-3 w-3" />
                  <span className="truncate max-w-[180px]">
                    {voice.name.replace("Microsoft ", "").replace(" Online (Natural)", "")}
                  </span>
                  <span className="text-xs text-muted-foreground">{voice.locale}</span>
                </div>
              </SelectItem>
            ))}
          </SelectGroup>
        )}

        {showRegisteredVoices && (
          <SelectGroup>
            <SelectLabel className="flex items-center gap-2">
              <Server className="h-3 w-3" />
              {currentRegisteredEngine?.engine_name} Voices
            </SelectLabel>
            {registeredBuiltinVoices.map((voice) => (
              <SelectItem key={`remote:${voice.id}`} value={`remote:${voice.id}`}>
                <div className="flex items-center gap-2">
                  <Server className="h-3 w-3" />
                  {voice.name}
                  {voice.language && <span className="text-xs text-muted-foreground">{voice.language}</span>}
                </div>
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        
        {voiceSamples.length > 0 && (
          <SelectGroup>
            <SelectLabel className="flex items-center gap-2">
              <Mic className="h-3 w-3" />
              Custom Voices
            </SelectLabel>
            {voiceSamples.map((sample) => (
              <SelectItem key={sample.id} value={sample.id}>
                <div className="flex items-center gap-2">
                  <Mic className="h-3 w-3" />
                  {sample.name}
                </div>
              </SelectItem>
            ))}
          </SelectGroup>
        )}
        
        {showLibraryVoices && (
          <SelectGroup>
            <SelectLabel className="flex items-center gap-2">
              <Library className="h-3 w-3" />
              Voice Library
            </SelectLabel>
            {libraryVoices.map((voice) => (
              <SelectItem key={voice.id} value={`library:${voice.id}`}>
                <div className="flex items-center gap-2">
                  <Library className="h-3 w-3" />
                  {voice.name}
                </div>
              </SelectItem>
            ))}
          </SelectGroup>
        )}

        <SelectGroup>
          <SelectItem value={UPLOAD_NEW_VALUE}>
            <div className="flex items-center gap-2 text-primary">
              <Plus className="h-3 w-3" />
              Upload New Voice...
            </div>
          </SelectItem>
        </SelectGroup>
      </>
    );
  };

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            Voice Assignment
          </CardTitle>
          <CardDescription className="mt-1">
            Assign voices to speakers and narrator
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className={speakers.length > 2 ? "h-[400px]" : ""}>
            <div className="space-y-6 pr-4">
              <div className="p-4 rounded-md bg-muted/50 border">
                <div className="flex items-center gap-2 mb-3">
                  <Volume2 className="h-4 w-4 text-primary" />
                  <Label className="font-medium">Narrator Voice</Label>
                </div>
                <Select
                  value={narratorVoiceId || "none"}
                  onValueChange={(v) => handleVoiceChange(v, { type: "narrator" })}
                >
                  <SelectTrigger data-testid="select-narrator-voice">
                    <SelectValue placeholder="Select narrator voice" />
                  </SelectTrigger>
                  <SelectContent>
                    {renderVoiceOptions()}
                  </SelectContent>
                </Select>
              </div>

              {speakers.length === 0 ? (
                <div className="text-center py-6 text-muted-foreground">
                  <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No speakers detected</p>
                  <p className="text-xs mt-1">Analyze text to detect dialogue speakers</p>
                </div>
              ) : (
                speakers.map((speaker) => {
                  const config = speakerConfigs[speaker] || {
                    name: speaker,
                    voiceSampleId: null,
                    pitchOffset: 0,
                    speedFactor: 1.0,
                  };

                  return (
                    <div key={speaker} className="p-4 rounded-md border space-y-4">
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-muted-foreground" />
                        <Label className="font-medium">{speaker}</Label>
                      </div>

                      <div className="space-y-2">
                        <Label className="text-xs text-muted-foreground">Voice Sample</Label>
                        <Select
                          value={config.voiceSampleId || "none"}
                          onValueChange={(v) => handleVoiceChange(v, { type: "speaker", speaker })}
                        >
                          <SelectTrigger data-testid={`select-voice-${speaker}`}>
                            <SelectValue placeholder="Select voice" />
                          </SelectTrigger>
                          <SelectContent>
                            {renderVoiceOptions()}
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs text-muted-foreground">
                            Pitch Offset
                          </Label>
                          <span className="text-xs font-mono">
                            {config.pitchOffset > 0 ? "+" : ""}
                            {config.pitchOffset} semitones
                          </span>
                        </div>
                        <Slider
                          value={[config.pitchOffset]}
                          min={-12}
                          max={12}
                          step={1}
                          onValueChange={([v]) =>
                            onUpdateSpeakerConfig(speaker, { pitchOffset: v })
                          }
                          data-testid={`slider-pitch-${speaker}`}
                        />
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs text-muted-foreground">
                            Speed Factor
                          </Label>
                          <span className="text-xs font-mono">
                            {config.speedFactor.toFixed(2)}x
                          </span>
                        </div>
                        <Slider
                          value={[config.speedFactor]}
                          min={0.5}
                          max={2.0}
                          step={0.05}
                          onValueChange={([v]) =>
                            onUpdateSpeakerConfig(speaker, { speedFactor: v })
                          }
                          data-testid={`slider-speed-${speaker}`}
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      <Dialog open={uploadDialogOpen} onOpenChange={(open) => {
        if (!open) {
          setUploadDialogOpen(false);
          setUploadName("");
          setUploadFile(null);
          setUploadTarget(null);
        }
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload New Voice</DialogTitle>
            <DialogDescription>
              Upload a 7-20 second audio clip for voice cloning. Clear recordings work best.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="voice-upload-name">Voice Name</Label>
              <Input
                id="voice-upload-name"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                placeholder="e.g., Deep Narrator, Female Lead"
                data-testid="input-upload-voice-name"
              />
            </div>
            <div className="grid gap-2">
              <Label>Audio File</Label>
              <input
                ref={fileInputRef}
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                data-testid="input-upload-voice-file"
              />
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => fileInputRef.current?.click()}
                data-testid="button-select-upload-voice-file"
              >
                <Upload className="h-4 w-4 mr-2" />
                {uploadFile ? uploadFile.name : "Select audio file..."}
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={handleUploadSubmit}
              disabled={!uploadFile || !uploadName.trim() || isUploading}
              data-testid="button-submit-upload-voice"
            >
              {isUploading ? "Uploading..." : "Upload Voice"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
