import { useState, useCallback, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookAudio, Sparkles, Wand2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import { TextInput } from "@/components/TextInput";
import { VoiceSampleManager } from "@/components/VoiceSampleManager";
import { VoiceLibrary } from "@/components/VoiceLibrary";
import { TextPreview } from "@/components/TextPreview";
import { SpeakerAssignment } from "@/components/SpeakerAssignment";
import { AudioPlayer } from "@/components/AudioPlayer";
import { GenerationProgress } from "@/components/GenerationProgress";
import { SettingsPanel } from "@/components/SettingsPanel";
import { ThemeToggle } from "@/components/ThemeToggle";
import type { TextSegment, VoiceSample, SpeakerConfig, ParseTextResponse, LibraryVoice } from "@shared/schema";

export default function Home() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Text state
  const [inputText, setInputText] = useState("");
  const [segments, setSegments] = useState<TextSegment[]>([]);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  // Voice state
  const [selectedVoiceId, setSelectedVoiceId] = useState<string | null>(null);
  const [narratorVoiceId, setNarratorVoiceId] = useState<string | null>(null);
  const [speakerConfigs, setSpeakerConfigs] = useState<Record<string, SpeakerConfig>>({});

  // Settings state
  const [exaggeration, setExaggeration] = useState(0.5);
  const [pauseDuration, setPauseDuration] = useState(500);

  // Generation state
  const [generationStatus, setGenerationStatus] = useState<"idle" | "processing" | "completed" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [currentSegment, setCurrentSegment] = useState(0);
  const [totalSegments, setTotalSegments] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [audioUrl, setAudioUrl] = useState<string | null>(null);

  // Parse progress state
  const [parseProgress, setParseProgress] = useState(0);
  const [parseTotalChunks, setParseTotalChunks] = useState(0);
  const [parseCurrentChunk, setParseCurrentChunk] = useState(0);
  const [isParsingStreaming, setIsParsingStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch voice samples
  const { data: voiceSamples = [] } = useQuery<VoiceSample[]>({
    queryKey: ["/api/voices"],
  });

  // Fetch voice library
  const { data: libraryVoices = [], isLoading: isLibraryLoading } = useQuery<LibraryVoice[]>({
    queryKey: ["/api/voice-library"],
  });

  // Selected library voice
  const [selectedLibraryVoiceId, setSelectedLibraryVoiceId] = useState<string | null>(null);

  // Get detected speakers
  const detectedSpeakers = Array.from(new Set(segments.filter((s) => s.speaker).map((s) => s.speaker!)));

  // Parse text mutation (supports both LLM and basic heuristic parsing)
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
      
      // Initialize speaker configs
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

  // Upload voice sample mutation
  const uploadVoiceMutation = useMutation({
    mutationFn: async ({ name, file }: { name: string; file: File }) => {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("file", file);
      
      const response = await fetch("/api/voices/upload", {
        method: "POST",
        body: formData,
      });
      
      if (!response.ok) {
        throw new Error("Failed to upload voice sample");
      }
      
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/voices"] });
      toast({
        title: "Voice uploaded",
        description: "Voice sample added successfully",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Upload failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  // Delete voice sample mutation
  const deleteVoiceMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiRequest("DELETE", `/api/voices/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/voices"] });
      toast({
        title: "Voice deleted",
        description: "Voice sample removed successfully",
      });
    },
  });

  // Generate audio mutation
  const generateAudioMutation = useMutation({
    mutationFn: async () => {
      setGenerationStatus("processing");
      setProgress(0);
      setCurrentSegment(0);
      setTotalSegments(segments.length);
      setStatusMessage("Starting audio generation...");

      const response = await apiRequest("POST", "/api/generate", {
        segments,
        config: {
          narratorVoiceId,
          defaultExaggeration: exaggeration,
          pauseBetweenSegments: pauseDuration,
          speakers: speakerConfigs,
        },
      });

      return await response.json() as { audioUrl: string };
    },
    onSuccess: (data) => {
      setAudioUrl(data.audioUrl);
      setGenerationStatus("completed");
      setProgress(100);
      setStatusMessage("Audio generation complete!");
      toast({
        title: "Audiobook ready",
        description: "Your audiobook has been generated successfully",
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

  // Streaming parse function for LLM mode
  const parseWithStreaming = useCallback(async (text: string, model?: string, knownSpeakers?: string[]) => {
    // Cancel any existing parse
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
      
      // Check if it's a streaming response or fallback JSON
      const contentType = response.headers.get('Content-Type') || '';
      if (!contentType.includes('text/event-stream')) {
        // Fallback response (non-streaming)
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
      
      // Handle SSE stream
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
        
        // Process complete SSE messages
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer
        
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
                
                // Add new segments incrementally
                setSegments(prev => [...prev, ...data.segments]);
                
                // Update detected speakers
                if (data.detectedSpeakers) {
                  data.detectedSpeakers.forEach((s: string) => accumulatedSpeakers.add(s));
                }
              }
              
              if (data.type === 'complete') {
                setParseProgress(100);
                
                // Finalize speaker configs
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
        return; // Cancelled, ignore
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

  // Handlers
  const handleAnalyze = useCallback((useLLM: boolean, model?: string, knownSpeakers?: string[]) => {
    if (inputText.trim()) {
      if (useLLM) {
        // Use streaming for LLM parsing
        parseWithStreaming(inputText, model, knownSpeakers);
      } else {
        // Use regular mutation for basic parsing
        parseTextMutation.mutate({ text: inputText, useLLM: false });
      }
    }
  }, [inputText, parseTextMutation, parseWithStreaming]);

  const handleUploadVoice = useCallback(async (name: string, file: File) => {
    await uploadVoiceMutation.mutateAsync({ name, file });
  }, [uploadVoiceMutation]);

  const handleDeleteVoice = useCallback((id: string) => {
    deleteVoiceMutation.mutate(id);
  }, [deleteVoiceMutation]);

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
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 items-center justify-between gap-4 px-4 mx-auto">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center h-10 w-10 rounded-md bg-primary text-primary-foreground">
              <BookAudio className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-semibold">Narrator AI</h1>
              <p className="text-xs text-muted-foreground hidden sm:block">Text to Audiobook Generator</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              onClick={handleGenerate}
              disabled={!canGenerate}
              className="gap-2"
              data-testid="button-generate-audio"
            >
              <Wand2 className="h-4 w-4" />
              <span className="hidden sm:inline">Generate Audiobook</span>
              <span className="sm:hidden">Generate</span>
            </Button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="container mx-auto px-4 py-6">
        {/* Progress indicator (shown when processing) */}
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

        {/* Audio player (shown when audio available) */}
        {audioUrl && (
          <div className="mb-6">
            <AudioPlayer
              audioUrl={audioUrl}
              title="Generated Audiobook"
              onDownload={handleDownload}
            />
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left column: Text input and preview */}
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

          {/* Right column: Voice samples, speaker assignment, settings */}
          <div className="flex flex-col gap-6">
            <VoiceLibrary
              voices={libraryVoices}
              selectedId={selectedLibraryVoiceId}
              onSelect={setSelectedLibraryVoiceId}
              isLoading={isLibraryLoading}
            />

            <VoiceSampleManager
              samples={voiceSamples}
              selectedId={selectedVoiceId}
              onSelect={setSelectedVoiceId}
              onUpload={handleUploadVoice}
              onDelete={handleDeleteVoice}
            />

            {detectedSpeakers.length > 0 && (
              <SpeakerAssignment
                speakers={detectedSpeakers}
                voiceSamples={voiceSamples}
                libraryVoices={libraryVoices}
                speakerConfigs={speakerConfigs}
                narratorVoiceId={narratorVoiceId}
                onUpdateSpeakerConfig={handleUpdateSpeakerConfig}
                onUpdateNarratorVoice={setNarratorVoiceId}
              />
            )}

            <SettingsPanel
              exaggeration={exaggeration}
              pauseDuration={pauseDuration}
              onExaggerationChange={setExaggeration}
              onPauseDurationChange={setPauseDuration}
            />
          </div>
        </div>

        {/* Empty state for initial load */}
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
      </main>
    </div>
  );
}
