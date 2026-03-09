import { Users, Mic, Volume2, Library, Globe } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { ScrollArea } from "@/components/ui/scroll-area";
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
import type { VoiceSample, SpeakerConfig, LibraryVoice, EdgeVoice, TTSEngine } from "@shared/schema";

interface SpeakerAssignmentProps {
  speakers: string[];
  voiceSamples: VoiceSample[];
  libraryVoices: LibraryVoice[];
  edgeVoices: EdgeVoice[];
  ttsEngine: TTSEngine;
  speakerConfigs: Record<string, SpeakerConfig>;
  narratorVoiceId: string | null;
  onUpdateSpeakerConfig: (speaker: string, config: Partial<SpeakerConfig>) => void;
  onUpdateNarratorVoice: (voiceId: string | null) => void;
}

export function SpeakerAssignment({
  speakers,
  voiceSamples,
  libraryVoices,
  edgeVoices,
  ttsEngine,
  speakerConfigs,
  narratorVoiceId,
  onUpdateSpeakerConfig,
  onUpdateNarratorVoice,
}: SpeakerAssignmentProps) {
  const renderVoiceOptions = () => {
    const showEdgeVoices = ttsEngine === "edge-tts" && edgeVoices.length > 0;
    const showLibraryVoices = isVoiceCloningEngine(ttsEngine) && libraryVoices.length > 0;
    
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
        
        {voiceSamples.length > 0 && (
          <SelectGroup>
            <SelectLabel className="flex items-center gap-2">
              <Mic className="h-3 w-3" />
              Uploaded Voices
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
              Voice Library (Chatterbox)
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
      </>
    );
  };
  return (
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
        <ScrollArea className="h-[300px]">
          <div className="space-y-6 pr-4">
            {/* Narrator voice */}
            <div className="p-4 rounded-md bg-muted/50 border">
              <div className="flex items-center gap-2 mb-3">
                <Volume2 className="h-4 w-4 text-primary" />
                <Label className="font-medium">Narrator Voice</Label>
              </div>
              <Select
                value={narratorVoiceId || "none"}
                onValueChange={(v) => onUpdateNarratorVoice(v === "none" ? null : v)}
              >
                <SelectTrigger data-testid="select-narrator-voice">
                  <SelectValue placeholder="Select narrator voice" />
                </SelectTrigger>
                <SelectContent>
                  {renderVoiceOptions()}
                </SelectContent>
              </Select>
            </div>

            {/* Speaker voices */}
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
                        onValueChange={(v) =>
                          onUpdateSpeakerConfig(speaker, {
                            voiceSampleId: v === "none" ? null : v,
                          })
                        }
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
  );
}
