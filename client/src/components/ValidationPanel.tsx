import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, Play, RefreshCw, Loader2, RotateCcw, Wand2, CheckSquare, ChevronsUpDown, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { ProjectData } from "@shared/schema";

interface ValidationConfig {
  sttModel: string;
  algorithms: string[];
  combinationMethod: string;
  dropWorstN: number;
  similarityCutoff: number;
  autoRegenerate: boolean;
  usePhonetic: boolean;
}

interface ValidationResults {
  results: Array<{
    chunkId: string;
    chunkText: string;
    combinedScore: number;
    isFlagged: boolean;
    isRegenerated: boolean;
  }>;
  jobStatus: string | null;
  jobId: string | null;
  jobProgress: number;
  hasResults?: boolean;
}

const ALGORITHM_LABELS: Record<string, string> = {
  sequence_matcher: "SequenceMatcher",
  levenshtein: "Levenshtein",
  token_sort: "Token Sort",
  jaro_winkler: "Jaro-Winkler",
  wer: "WER Similarity",
};

const COMBINATION_METHODS = [
  { value: "average", label: "Average Similarity" },
  { value: "max", label: "Max Similarity" },
  { value: "min", label: "Min Similarity" },
];

const DEFAULT_CONFIG: ValidationConfig = {
  sttModel: "google/gemini-2.5-flash",
  algorithms: ["sequence_matcher", "levenshtein", "token_sort"],
  combinationMethod: "average",
  dropWorstN: 0,
  similarityCutoff: 0.80,
  autoRegenerate: false,
  usePhonetic: false,
};

interface ValidationPanelProps {
  project: ProjectData;
  onRefresh: () => void;
}

export function ValidationPanel({ project, onRefresh }: ValidationPanelProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [config, setConfig] = useState<ValidationConfig>(DEFAULT_CONFIG);
  const [configLoaded, setConfigLoaded] = useState(false);
  const [modelOpen, setModelOpen] = useState(false);

  const { data: configData } = useQuery<{ config: ValidationConfig; algorithmLabels: Record<string, string> }>({
    queryKey: ["/api/projects", project.id, "validation/config"],
  });

  const { data: sttModelsData } = useQuery<{ models: { id: string; name: string; endpoint: "chat" | "transcriptions" }[]; ready: boolean; error?: string }>({
    queryKey: ["/api/validation/stt-models"],
    staleTime: 5 * 60 * 1000,
  });

  const { data: resultsData } = useQuery<ValidationResults>({
    queryKey: ["/api/projects", project.id, "validation/results"],
    refetchInterval: (query) => {
      const status = query.state.data?.jobStatus;
      return status === "processing" || status === "pending" ? 2000 : false;
    },
  });

  useEffect(() => {
    if (configData?.config && !configLoaded) {
      setConfig(configData.config);
      setConfigLoaded(true);
    }
  }, [configData, configLoaded]);

  const saveConfigMutation = useMutation({
    mutationFn: async (cfg: ValidationConfig) => {
      const res = await apiRequest("POST", `/api/projects/${project.id}/validation/config`, cfg);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id, "validation/config"] });
    },
  });

  const startMutation = useMutation({
    mutationFn: async () => {
      await saveConfigMutation.mutateAsync(config);
      const res = await apiRequest("POST", `/api/projects/${project.id}/validation/start`, {});
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id, "validation/results"] });
      toast({ title: "Validation started", description: "STT transcription is running in the background." });
    },
    onError: (e: Error) => {
      toast({ title: "Failed to start validation", description: e.message, variant: "destructive" });
    },
  });

  const applyMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/projects/${project.id}/validation/apply`, {
        algorithms: config.algorithms,
        combinationMethod: config.combinationMethod,
        dropWorstN: config.dropWorstN,
        similarityCutoff: config.similarityCutoff,
      });
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id, "validation/results"] });
      toast({ title: "Settings applied", description: `Re-evaluated ${data.updated} chunks.` });
      onRefresh();
    },
    onError: (e: Error) => {
      toast({ title: "Apply failed", description: e.message, variant: "destructive" });
    },
  });

  const regenerateMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/projects/${project.id}/validation/regenerate`, {});
      return res.json();
    },
    onSuccess: (data) => {
      if (data.message) {
        toast({ title: "Nothing to regenerate", description: data.message });
      } else {
        queryClient.invalidateQueries({ queryKey: ["/api/projects", project.id, "validation/results"] });
        queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
        toast({ title: "Regeneration started", description: `${data.count} chunk(s) queued for re-generation.` });
        onRefresh();
      }
    },
    onError: (e: Error) => {
      toast({ title: "Regeneration failed", description: e.message, variant: "destructive" });
    },
  });

  const toggleAlgorithm = (algo: string) => {
    setConfig((prev) => {
      const has = prev.algorithms.includes(algo);
      const next = has ? prev.algorithms.filter((a) => a !== algo) : [...prev.algorithms, algo];
      return { ...prev, algorithms: next.length > 0 ? next : prev.algorithms };
    });
  };

  const jobRunning = resultsData?.jobStatus === "processing" || resultsData?.jobStatus === "pending";
  const flaggedCount = (resultsData?.results ?? []).filter((r) => r.isFlagged && !r.isRegenerated).length;
  const totalValidated = resultsData?.results.length ?? 0;
  const hasResults = totalValidated > 0;
  const progress = jobRunning ? Math.round((resultsData?.jobProgress ?? 0) * 100) : null;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-base font-semibold">Audio Validation</h2>
      </div>

      {jobRunning && (
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Validation running… {progress !== null && `${progress}%`}
          </div>
          {progress !== null && <Progress value={progress} className="h-1.5" />}
        </div>
      )}

      {resultsData?.jobStatus === "completed" && (
        <div className="rounded-md border p-3 bg-muted/40 text-sm flex items-center gap-3">
          <CheckSquare className="h-4 w-4 text-green-500 shrink-0" />
          <span>
            Last run: <strong>{totalValidated}</strong> chunks validated,{" "}
            <strong>{flaggedCount}</strong> flagged
          </span>
        </div>
      )}

      <Separator />

      {/* STT Model */}
      <div className="space-y-2">
        <Label>STT Model (via OpenRouter)</Label>
        {sttModelsData?.ready && sttModelsData.models.length > 0 ? (
          <>
            <Popover open={modelOpen} onOpenChange={setModelOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={modelOpen}
                  className="w-full justify-between font-normal"
                >
                  <span className="truncate">
                    {sttModelsData.models.find((m) => m.id === config.sttModel)?.name ?? config.sttModel}
                  </span>
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search models…" />
                  <CommandList>
                    <CommandEmpty>No models found.</CommandEmpty>
                    <CommandGroup>
                      {sttModelsData.models.map((m) => (
                        <CommandItem
                          key={m.id}
                          value={`${m.name} ${m.id}`}
                          onSelect={() => {
                            setConfig((p) => ({ ...p, sttModel: m.id }));
                            setModelOpen(false);
                          }}
                        >
                          <Check className={cn("mr-2 h-4 w-4 shrink-0", config.sttModel === m.id ? "opacity-100" : "opacity-0")} />
                          <div className="flex flex-col min-w-0 flex-1">
                            <span className="truncate">{m.name}</span>
                            <span className="text-xs text-muted-foreground truncate">{m.id}</span>
                          </div>
                          <span className={cn(
                            "ml-2 shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium",
                            m.endpoint === "transcriptions"
                              ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
                              : "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300"
                          )}>
                            {m.endpoint === "transcriptions" ? "STT" : "LLM"}
                          </span>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
            <p className="text-xs text-muted-foreground">
              {(() => {
                const selected = sttModelsData.models.find((m) => m.id === config.sttModel);
                if (!selected) return `${sttModelsData.models.length} audio-capable models loaded.`;
                return selected.endpoint === "transcriptions"
                  ? "Uses /audio/transcriptions (dedicated STT model)."
                  : "Uses /chat/completions with base64 audio (multimodal LLM).";
              })()}
            </p>
          </>
        ) : (
          <>
            <Input
              value={config.sttModel}
              onChange={(e) => setConfig((p) => ({ ...p, sttModel: e.target.value }))}
              placeholder="e.g. google/gemini-2.5-flash"
            />
            <p className="text-xs text-muted-foreground">
              {sttModelsData && !sttModelsData.ready
                ? "Model list loading… Enter a model ID manually."
                : "Must be a multimodal model that accepts audio input."}
            </p>
          </>
        )}
      </div>

      {/* Algorithms */}
      <div className="space-y-2">
        <Label>Similarity Algorithms</Label>
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(ALGORITHM_LABELS).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={config.algorithms.includes(key)}
                onCheckedChange={() => toggleAlgorithm(key)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      {/* Combination method + drop worst */}
      {config.algorithms.length > 1 && (
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Combine Scores Using</Label>
            <Select
              value={config.combinationMethod}
              onValueChange={(v) => setConfig((p) => ({ ...p, combinationMethod: v }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {COMBINATION_METHODS.map((m) => (
                  <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Drop Worst N Scores</Label>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => setConfig((p) => ({ ...p, dropWorstN: Math.max(0, p.dropWorstN - 1) }))}
              >−</Button>
              <Input
                type="number"
                min={0}
                max={Math.max(0, config.algorithms.length - 1)}
                className="w-16 text-center"
                value={config.dropWorstN}
                onChange={(e) => {
                  const v = Math.max(0, Math.min(parseInt(e.target.value) || 0, config.algorithms.length - 1));
                  setConfig((p) => ({ ...p, dropWorstN: v }));
                }}
              />
              <Button
                variant="outline"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => setConfig((p) => ({ ...p, dropWorstN: Math.min(p.algorithms.length - 1, p.dropWorstN + 1) }))}
              >+</Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {config.dropWorstN > 0
                ? `Drops the ${config.dropWorstN} lowest score(s) before combining`
                : "All scores used"}
            </p>
          </div>
        </div>
      )}

      {/* Cutoff */}
      <div className="space-y-2">
        <Label>Similarity Cutoff</Label>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={0}
            max={1}
            step={0.01}
            className="w-24"
            value={config.similarityCutoff}
            onChange={(e) => {
              const v = Math.max(0, Math.min(1, parseFloat(e.target.value) || 0));
              setConfig((p) => ({ ...p, similarityCutoff: v }));
            }}
          />
          <span className="text-sm text-muted-foreground">
            Chunks below <strong>{(config.similarityCutoff * 100).toFixed(0)}%</strong> similarity are flagged
          </span>
        </div>
      </div>

      {/* Auto regenerate */}
      <div className="flex items-center gap-2">
        <Checkbox
          id="auto-regen"
          checked={config.autoRegenerate}
          onCheckedChange={(v) => setConfig((p) => ({ ...p, autoRegenerate: !!v }))}
        />
        <Label htmlFor="auto-regen" className="cursor-pointer font-normal">
          Automatically regenerate flagged chunks after validation
        </Label>
      </div>
      {config.autoRegenerate && (
        <p className="text-xs text-muted-foreground pl-6">
          Recommended only after you've dialled in the cutoff on a test run. Disable to review results first.
        </p>
      )}

      {/* Phonetic preprocessing */}
      <div className="flex items-center gap-2">
        <Checkbox
          id="use-phonetic"
          checked={config.usePhonetic}
          onCheckedChange={(v) => setConfig((p) => ({ ...p, usePhonetic: !!v }))}
        />
        <Label htmlFor="use-phonetic" className="cursor-pointer font-normal">
          Phonetic preprocessing (Double Metaphone)
        </Label>
      </div>
      {config.usePhonetic && (
        <p className="text-xs text-muted-foreground pl-6">
          Converts both texts to phonetic codes before comparing. Useful when the STT model transcribes words that sound correct but are spelled differently.
        </p>
      )}

      <Separator />

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2">
        <Button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending || jobRunning || config.algorithms.length === 0}
        >
          {startMutation.isPending || jobRunning
            ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Running…</>
            : <><Play className="h-4 w-4 mr-2" />Start Validation</>}
        </Button>

        {hasResults && (
          <Button
            variant="outline"
            onClick={() => applyMutation.mutate()}
            disabled={applyMutation.isPending || jobRunning}
          >
            {applyMutation.isPending
              ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Applying…</>
              : <><RefreshCw className="h-4 w-4 mr-2" />Apply Changes</>}
          </Button>
        )}

        {flaggedCount > 0 && (
          <Button
            variant="destructive"
            onClick={() => regenerateMutation.mutate()}
            disabled={regenerateMutation.isPending || jobRunning}
          >
            {regenerateMutation.isPending
              ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Queuing…</>
              : <><Wand2 className="h-4 w-4 mr-2" />Regenerate All Flagged ({flaggedCount})</>}
          </Button>
        )}
      </div>
    </div>
  );
}
