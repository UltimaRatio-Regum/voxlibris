import { useState, useRef } from "react";
import { Upload, FileText, Sparkles, Brain, ChevronDown, Users, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

interface TextInputProps {
  value: string;
  onChange: (text: string) => void;
  onAnalyze: (useLLM: boolean, model?: string, knownSpeakers?: string[]) => void;
  isAnalyzing: boolean;
  parseProgress?: number;
  parseCurrentChunk?: number;
  parseTotalChunks?: number;
}

const LLM_MODELS = [
  { id: "openai/gpt-5.2", name: "ChatGPT 5.2" },
  { id: "openai/chatgpt-4o-latest", name: "ChatGPT 4o" },
  { id: "openai/gpt-4o", name: "GPT-4o" },
  { id: "openai/gpt-4o-mini", name: "GPT-4o Mini" },
  { id: "meta-llama/llama-3.3-70b-instruct", name: "Llama 3.3 70B" },
  { id: "meta-llama/llama-3.1-8b-instruct", name: "Llama 3.1 8B" },
  { id: "mistralai/mistral-7b-instruct", name: "Mistral 7B" },
  { id: "qwen/qwen-2.5-72b-instruct", name: "Qwen 2.5 72B" },
  { id: "deepseek/deepseek-chat", name: "DeepSeek Chat" },
];

export function TextInput({ 
  value, 
  onChange, 
  onAnalyze, 
  isAnalyzing,
  parseProgress = 0,
  parseCurrentChunk = 0,
  parseTotalChunks = 0,
}: TextInputProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedModel, setSelectedModel] = useState(LLM_MODELS[0]);
  const [useLLM, setUseLLM] = useState(true);
  const [speakerInput, setSpeakerInput] = useState("");
  const [showSpeakerInput, setShowSpeakerInput] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const showProgress = isAnalyzing && parseTotalChunks > 0;

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      await readFile(files[0]);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      await readFile(files[0]);
    }
  };

  const readFile = async (file: File) => {
    const text = await file.text();
    onChange(text);
  };

  const handleAnalyze = () => {
    // Parse speaker names from comma-separated input
    const knownSpeakers = speakerInput
      .split(",")
      .map(s => s.trim())
      .filter(s => s.length > 0);
    
    onAnalyze(useLLM, useLLM ? selectedModel.id : undefined, knownSpeakers.length > 0 ? knownSpeakers : undefined);
  };

  const wordCount = value.trim() ? value.trim().split(/\s+/).length : 0;
  const charCount = value.length;
  const estimatedDuration = Math.ceil(wordCount / 150);

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              Input Text
            </CardTitle>
            <CardDescription className="mt-1">
              Paste your text or upload a file
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.rtf"
              className="hidden"
              onChange={handleFileSelect}
              data-testid="input-file-upload"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              data-testid="button-upload-file"
            >
              <Upload className="h-4 w-4 mr-2" />
              Upload
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-4">
        <div
          className={`flex-1 relative rounded-md border-2 border-dashed transition-colors ${
            isDragOver 
              ? "border-primary bg-primary/5" 
              : "border-muted-foreground/25"
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <Textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Paste your story, novel chapter, or any text here. The system will automatically detect dialogue, identify speakers, and apply appropriate emotional prosody..."
            className="h-full resize-none border-0 focus-visible:ring-0 bg-transparent min-h-[300px]"
            data-testid="textarea-text-input"
          />
          {!value && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-50">
              <div className="text-center">
                <Upload className="h-10 w-10 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">Drop a text file here</p>
              </div>
            </div>
          )}
        </div>
        
        {useLLM && (
          <Collapsible open={showSpeakerInput} onOpenChange={setShowSpeakerInput}>
            <CollapsibleTrigger asChild>
              <Button 
                variant="ghost" 
                size="sm" 
                className="gap-2 w-full justify-start text-muted-foreground hover:text-foreground"
                data-testid="button-toggle-speakers"
              >
                <Users className="h-4 w-4" />
                <span>Known speakers (optional)</span>
                <ChevronDown className={`h-3 w-3 ml-auto transition-transform ${showSpeakerInput ? "rotate-180" : ""}`} />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-2">
              <Input
                value={speakerInput}
                onChange={(e) => setSpeakerInput(e.target.value)}
                placeholder="Enter character names separated by commas (e.g., John, Mary, Narrator)"
                className="text-sm"
                data-testid="input-known-speakers"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Providing speaker names helps the AI identify who is speaking more accurately
              </p>
            </CollapsibleContent>
          </Collapsible>
        )}

        {showProgress && (
          <div className="space-y-2 p-3 rounded-md bg-primary/5 border border-primary/20" data-testid="parse-progress-container">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2 text-primary">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Analyzing text with AI...</span>
              </div>
              <span className="text-muted-foreground">
                Chunk {parseCurrentChunk} of {parseTotalChunks}
              </span>
            </div>
            <Progress value={parseProgress} className="h-2" data-testid="progress-parse" />
            <p className="text-xs text-muted-foreground">
              Processing large text in chunks for better accuracy
            </p>
          </div>
        )}

        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span data-testid="text-word-count">{wordCount.toLocaleString()} words</span>
            <span>{charCount.toLocaleString()} characters</span>
            {wordCount > 0 && (
              <span>~{estimatedDuration} min audio</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={useLLM ? "secondary" : "outline"}
              size="sm"
              onClick={() => setUseLLM(!useLLM)}
              className="gap-1"
              data-testid="button-toggle-llm"
            >
              <Brain className="h-4 w-4" />
              <span className="hidden sm:inline">{useLLM ? "AI Detection" : "Basic"}</span>
            </Button>
            
            {useLLM && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1" data-testid="button-select-model">
                    <span className="max-w-[100px] truncate">{selectedModel.name}</span>
                    <ChevronDown className="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {LLM_MODELS.map((model) => (
                    <DropdownMenuItem
                      key={model.id}
                      onClick={() => setSelectedModel(model)}
                      data-testid={`menu-item-model-${model.name.replace(/\s+/g, '-').toLowerCase()}`}
                    >
                      {model.name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            <Button 
              onClick={handleAnalyze} 
              disabled={!value.trim() || isAnalyzing}
              data-testid="button-analyze-text"
            >
              {isAnalyzing ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4 mr-2" />
              )}
              {isAnalyzing ? "Analyzing..." : "Analyze Text"}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
