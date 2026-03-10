import { useState, useCallback, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import { TextInput } from "@/components/TextInput";
import { TextPreview } from "@/components/TextPreview";
import { SpeakerAssignment } from "@/components/SpeakerAssignment";
import { AudioPlayer } from "@/components/AudioPlayer";
import { GenerationProgress } from "@/components/GenerationProgress";
import { SettingsPanel, type RegisteredEngine } from "@/components/SettingsPanel";
import type { TextSegment, VoiceSample, SpeakerConfig, ParseTextResponse, LibraryVoice, TTSEngine, EdgeVoice } from "@shared/schema";

export function AdvancedTab() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const [inputText, setInputText] = useState("");
  const [segments, setSegments] = useState<TextSegment[]>([]);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  const [narratorVoiceId, setNarratorVoiceId] = useState<string | null>(null);
  const [speakerConfigs, setSpeakerConfigs] = useState<Record<string, SpeakerConfig>>({});

  const [exaggeration, setExaggeration] = useState(0.5);
  const [pauseDuration, setPauseDuration] = useState(500);
  const [ttsEngine, setTTSEngine] = useState<TTSEngine>("edge-tts");

  const [generationStatus, setGenerationStatus] = useState<"idle" | "processing" | "completed" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [currentSegment, setCurrentSegment] = useState(0);
  const [totalSegments, setTotalSegments] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  const [parseProgress, setParseProgress] = useState(0);
  const [parseTotalChunks, setParseTotalChunks] = useState(0);
  const [parseCurrentChunk, setParseCurrentChunk] = useState(0);
  const [isParsingStreaming, setIsParsingStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const { data: voiceSamples = [] } = useQuery<VoiceSample[]>({
    queryKey: ["/api/voices"],
  });

  const { data: libraryVoices = [] } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library"],
  });

  const { data: edgeVoicesData } = useQuery<{ voices: EdgeVoice[], presets: Record<string, string> }>({
    queryKey: ["/api/edge-voices"],
    enabled: ttsEngine === "edge-tts",
  });
  const edgeVoices = edgeVoicesData?.voices ?? [];

  const { data: registeredEngines = [] } = useQuery<RegisteredEngine[]>({
    queryKey: ["/api/tts-engines"],
  });

  const detectedSpeakers = Array.from(new Set(segments.filter((s) => s.speaker).map((s) => s.speaker!)));

  const parseTextMutation = useMutation({
    mutationFn: async ({ text, useLLM, model, knownSpeakers }: { 
      text: string; 
      useLLM: boolean; 
      model?: string;
      knownSpeakers?: string[];
    }) => {
      const endpoint = useLLM ? "/api/parse-text-llm" : "/api/parse-text";
      const body = useLLM ? { text, model, knownSpeakers } : { text };
      const response = await apiRequest("POST", endpoint, body);
      return await response.json() as ParseTextResponse;
    },
    onSuccess: (data) => {
      setSegments(data.segments);
      
      const newConfigs: Record<string, SpeakerConfig> = {};
      data.detectedSpeakers.forEach((speaker) => {
        newConfigs[speaker] = {
          name: speaker,
          voiceSampleId: null,
          pitchOffset: 0,
          speedFactor: 1.0,
        };
      });
      setSpeakerConfigs(newConfigs);

      toast({
        title: "Text analyzed",
        description: `Found ${data.segments.length} segments and ${data.detectedSpeakers.length} speakers`,
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Analysis failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const generateAudioMutation = useMutation({
    mutationFn: async () => {
      setGenerationStatus("processing");
      setProgress(0);
      setCurrentSegment(0);
      setTotalSegments(segments.length);
      setStatusMessage("Creating audio generation job...");

      const response = await apiRequest('POST', '/api/jobs', {
        title: inputText.slice(0, 50) || "Untitled Audiobook",
        segments: segments.map(s => ({
          id: s.id,
          text: s.text,
          type: s.type,
          speaker: s.speaker,
          sentiment: s.sentiment,
        })),
        config: {
          narratorVoiceId,
          defaultExaggeration: exaggeration,
          pauseBetweenSegments: pauseDuration,
          speakers: speakerConfigs,
          ttsEngine,
        },
      });

      const data = await response.json();
      return { jobId: data.jobId };
    },
    onSuccess: () => {
      setGenerationStatus("idle");
      setStatusMessage("");
      queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
      toast({
        title: "Generation started",
        description: "Your audiobook is being generated in the background. Check the Job Monitor tab for progress.",
      });
    },
    onError: (error: Error) => {
      setGenerationStatus("error");
      setStatusMessage(`Error: ${error.message}`);
      toast({
        title: "Generation failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const parseWithStreaming = useCallback(async (text: string, model?: string, knownSpeakers?: string[]) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    const controller = new AbortController();
    abortControllerRef.current = controller;
    
    setIsParsingStreaming(true);
    setParseProgress(0);
    setParseCurrentChunk(0);
    setParseTotalChunks(0);
    setSegments([]);
    
    const accumulatedSpeakers = new Set<string>();
    
    try {
      const response = await fetch('/api/parse-text-llm-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, model, knownSpeakers }),
        signal: controller.signal,
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to parse text');
      }
      
      const contentType = response.headers.get('Content-Type') || '';
      if (!contentType.includes('text/event-stream')) {
        const data = await response.json() as ParseTextResponse;
        setSegments(data.segments);
        
        const newConfigs: Record<string, SpeakerConfig> = {};
        data.detectedSpeakers.forEach((speaker) => {
          newConfigs[speaker] = {
            name: speaker,
            voiceSampleId: null,
            pitchOffset: 0,
            speedFactor: 1.0,
          };
        });
        setSpeakerConfigs(newConfigs);
        setParseProgress(100);
        
        toast({
          title: "Text analyzed (fallback)",
          description: `Found ${data.segments.length} segments and ${data.detectedSpeakers.length} speakers`,
        });
        return;
      }
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (!reader) {
        throw new Error('No response body');
      }
      
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === 'progress') {
                setParseTotalChunks(data.totalChunks);
                setParseCurrentChunk(data.chunkIndex);
                setParseProgress(0);
              }
              
              if (data.type === 'chunk') {
                setParseCurrentChunk(data.chunkIndex);
                const progressPct = Math.round((data.chunkIndex / data.totalChunks) * 100);
                setParseProgress(progressPct);
                
                setSegments(prev => [...prev, ...data.segments]);
                
                if (data.detectedSpeakers) {
                  data.detectedSpeakers.forEach((s: string) => accumulatedSpeakers.add(s));
                }
              }
              
              if (data.type === 'complete') {
                setParseProgress(100);
                
                const newConfigs: Record<string, SpeakerConfig> = {};
                accumulatedSpeakers.forEach((speaker) => {
                  newConfigs[speaker] = {
                    name: speaker,
                    voiceSampleId: null,
                    pitchOffset: 0,
                    speedFactor: 1.0,
                  };
                });
                setSpeakerConfigs(newConfigs);
                
                toast({
                  title: "Text analyzed",
                  description: `Found ${data.totalSegments} segments and ${accumulatedSpeakers.size} speakers`,
                });
              }
              
              if (data.type === 'error') {
                throw new Error(data.error);
              }
            } catch (parseError) {
              if (parseError instanceof SyntaxError) {
                console.warn('Invalid SSE JSON:', line);
              } else {
                throw parseError;
              }
            }
          }
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        return;
      }
      toast({
        title: "Analysis failed",
        description: (error as Error).message,
        variant: "destructive",
      });
    } finally {
      setIsParsingStreaming(false);
      abortControllerRef.current = null;
    }
  }, [toast]);

  const handleAnalyze = useCallback((useLLM: boolean, model?: string, knownSpeakers?: string[]) => {
    if (inputText.trim()) {
      if (useLLM) {
        parseWithStreaming(inputText, model, knownSpeakers);
      } else {
        parseTextMutation.mutate({ text: inputText, useLLM: false });
      }
    }
  }, [inputText, parseTextMutation, parseWithStreaming]);

  const handleVoiceUploaded = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["/api/voices"] });
    queryClient.invalidateQueries({ queryKey: ["/api/custom-voices"] });
    toast({
      title: "Voice uploaded",
      description: "Voice sample added successfully",
    });
  }, [queryClient, toast]);

  const handleUpdateSpeakerConfig = useCallback((speaker: string, config: Partial<SpeakerConfig>) => {
    setSpeakerConfigs((prev) => ({
      ...prev,
      [speaker]: { ...prev[speaker], ...config },
    }));
  }, []);

  const handleGenerate = useCallback(() => {
    if (segments.length === 0) {
      toast({
        title: "No segments",
        description: "Please analyze text first before generating audio",
        variant: "destructive",
      });
      return;
    }
    generateAudioMutation.mutate();
  }, [segments, generateAudioMutation, toast]);

  const handleDownload = useCallback(() => {
    if (audioUrl) {
      const a = document.createElement("a");
      a.href = audioUrl;
      a.download = "audiobook.wav";
      a.click();
    }
  }, [audioUrl]);

  const canGenerate = segments.length > 0 && generationStatus !== "processing";

  return (
    <div className="space-y-6">
      {generationStatus !== "idle" && (
        <div className="mb-6">
          <GenerationProgress
            status={generationStatus}
            progress={progress}
            currentSegment={currentSegment}
            totalSegments={totalSegments}
            statusMessage={statusMessage}
          />
        </div>
      )}

      {audioUrl && (
        <div className="mb-6">
          <AudioPlayer
            audioUrl={audioUrl}
            title="Generated Audiobook"
            onDownload={handleDownload}
          />
        </div>
      )}

      <div className="flex justify-end mb-4">
        <Button
          onClick={handleGenerate}
          disabled={!canGenerate}
          className="gap-2"
          data-testid="button-generate-audio"
        >
          <Wand2 className="h-4 w-4" />
          Generate Audiobook
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-6">
          <TextInput
            value={inputText}
            onChange={setInputText}
            onAnalyze={handleAnalyze}
            isAnalyzing={parseTextMutation.isPending || isParsingStreaming}
            parseProgress={parseProgress}
            parseCurrentChunk={parseCurrentChunk}
            parseTotalChunks={parseTotalChunks}
          />
          
          {segments.length > 0 && (
            <TextPreview
              segments={segments}
              selectedSegmentId={selectedSegmentId}
              onSelectSegment={setSelectedSegmentId}
            />
          )}
        </div>

        <div className="flex flex-col gap-6">
          <SettingsPanel
            exaggeration={exaggeration}
            pauseDuration={pauseDuration}
            ttsEngine={ttsEngine}
            registeredEngines={registeredEngines}
            onExaggerationChange={setExaggeration}
            onPauseDurationChange={setPauseDuration}
            onTTSEngineChange={setTTSEngine}
          />

          {segments.length > 0 && (
            <SpeakerAssignment
              speakers={detectedSpeakers}
              voiceSamples={voiceSamples}
              libraryVoices={libraryVoices}
              edgeVoices={edgeVoices}
              ttsEngine={ttsEngine}
              registeredEngines={registeredEngines}
              speakerConfigs={speakerConfigs}
              narratorVoiceId={narratorVoiceId}
              onUpdateSpeakerConfig={handleUpdateSpeakerConfig}
              onUpdateNarratorVoice={setNarratorVoiceId}
              onVoiceUploaded={handleVoiceUploaded}
            />
          )}
        </div>
      </div>

      {segments.length === 0 && !inputText && (
        <div className="mt-12 text-center">
          <div className="inline-flex items-center justify-center h-16 w-16 rounded-full bg-primary/10 mb-4">
            <Sparkles className="h-8 w-8 text-primary" />
          </div>
          <h2 className="text-xl font-semibold mb-2">Create Your Audiobook</h2>
          <p className="text-muted-foreground max-w-md mx-auto">
            Paste your text or upload a file to get started. The AI will analyze dialogue, 
            detect speakers, and add emotional prosody to bring your story to life.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-2 w-2 rounded-full bg-green-500" />
              Voice cloning
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-2 w-2 rounded-full bg-blue-500" />
              Sentiment-based prosody
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-2 w-2 rounded-full bg-purple-500" />
              Multi-speaker support
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
