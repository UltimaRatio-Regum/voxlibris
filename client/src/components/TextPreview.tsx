import { BookOpen, Quote, User, AlertTriangle, Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { TextSegment } from "@shared/schema";

interface TextPreviewProps {
  segments: TextSegment[];
  selectedSegmentId: string | null;
  onSelectSegment: (id: string) => void;
}

function SpeakerConfidenceTooltip({ candidates }: { candidates: Record<string, number> }) {
  const entries = Object.entries(candidates).sort((a, b) => b[1] - a[1]);
  
  return (
    <div className="space-y-1">
      <p className="font-medium text-xs mb-2">Speaker Confidence</p>
      {entries.map(([speaker, confidence]) => (
        <div key={speaker} className="flex items-center justify-between gap-3 text-xs">
          <span>{speaker}</span>
          <div className="flex items-center gap-1">
            <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary transition-all" 
                style={{ width: `${confidence * 100}%` }}
              />
            </div>
            <span className="text-muted-foreground w-8">{Math.round(confidence * 100)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}

const sentimentColors: Record<string, string> = {
  positive: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20",
  negative: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20",
  neutral: "bg-gray-500/10 text-gray-700 dark:text-gray-400 border-gray-500/20",
  excited: "bg-yellow-500/10 text-yellow-700 dark:text-yellow-400 border-yellow-500/20",
  sad: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20",
  angry: "bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/20",
  fearful: "bg-purple-500/10 text-purple-700 dark:text-purple-400 border-purple-500/20",
};

export function TextPreview({
  segments,
  selectedSegmentId,
  onSelectSegment,
}: TextPreviewProps) {
  const dialogueCount = segments.filter((s) => s.type === "dialogue").length;
  const narrationCount = segments.filter((s) => s.type === "narration").length;
  const reviewCount = segments.filter((s) => s.needsReview).length;
  const speakers = Array.from(new Set(segments.filter((s) => s.speaker).map((s) => s.speaker as string)));

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-primary" />
              Parsed Segments
            </CardTitle>
            <CardDescription className="mt-1">
              Review and edit segment assignments
            </CardDescription>
          </div>
          {segments.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="secondary" className="border">
                <Quote className="h-3 w-3 mr-1" />
                {dialogueCount} dialogue
              </Badge>
              <Badge variant="secondary" className="border">
                <BookOpen className="h-3 w-3 mr-1" />
                {narrationCount} narration
              </Badge>
              {reviewCount > 0 && (
                <Badge variant="outline" className="border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="h-3 w-3 mr-1" />
                  {reviewCount} need review
                </Badge>
              )}
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col min-h-0">
        {segments.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <BookOpen className="h-10 w-10 mx-auto mb-3 opacity-50" />
              <p className="text-sm">No segments yet</p>
              <p className="text-xs mt-1">Analyze text to see parsed segments</p>
            </div>
          </div>
        ) : (
          <ScrollArea className="flex-1">
            <div className="space-y-2 pr-4">
              {segments.map((segment, index) => (
                <div
                  key={segment.id}
                  className={`p-3 rounded-md border cursor-pointer transition-all hover-elevate ${
                    selectedSegmentId === segment.id
                      ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                      : "border-border/50"
                  } ${segment.type === "dialogue" ? "pl-6 border-l-4 border-l-primary/50" : ""}`}
                  onClick={() => onSelectSegment(segment.id)}
                  data-testid={`segment-${segment.id}`}
                >
                  <div className="flex items-start gap-2 mb-2 flex-wrap">
                    <Badge 
                      variant="outline" 
                      className={`text-xs ${segment.type === "dialogue" ? "border-primary/50" : ""}`}
                    >
                      {segment.type === "dialogue" ? (
                        <Quote className="h-3 w-3 mr-1" />
                      ) : (
                        <BookOpen className="h-3 w-3 mr-1" />
                      )}
                      {segment.type}
                    </Badge>
                    {segment.speaker && segment.speakerCandidates && Object.keys(segment.speakerCandidates).length > 1 ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge 
                            variant="secondary" 
                            className={`text-xs cursor-help ${segment.needsReview ? "border-amber-500/50 bg-amber-500/10" : ""}`}
                          >
                            <User className="h-3 w-3 mr-1" />
                            {segment.speaker}
                            {segment.needsReview && <AlertTriangle className="h-3 w-3 ml-1 text-amber-600" />}
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs">
                          <SpeakerConfidenceTooltip candidates={segment.speakerCandidates} />
                        </TooltipContent>
                      </Tooltip>
                    ) : segment.speaker ? (
                      <Badge variant="secondary" className="text-xs">
                        <User className="h-3 w-3 mr-1" />
                        {segment.speaker}
                      </Badge>
                    ) : null}
                    {segment.needsReview && !segment.speaker && (
                      <Badge variant="outline" className="text-xs border-amber-500/50 bg-amber-500/10 text-amber-700 dark:text-amber-400">
                        <AlertTriangle className="h-3 w-3 mr-1" />
                        needs review
                      </Badge>
                    )}
                    {segment.sentiment && (
                      <Badge 
                        variant="outline" 
                        className={`text-xs ${sentimentColors[segment.sentiment.label] || ""}`}
                      >
                        {segment.sentiment.label}
                        <span className="ml-1 opacity-60">
                          {Math.round(segment.sentiment.score * 100)}%
                        </span>
                      </Badge>
                    )}
                    {segment.chunkId && (
                      <span className="text-xs text-muted-foreground">
                        ~{segment.approxDurationSeconds || 30}s
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground ml-auto">
                      #{index + 1}
                    </span>
                  </div>
                  <p className={`text-sm leading-relaxed ${
                    segment.type === "dialogue" ? "italic" : ""
                  }`}>
                    {segment.text}
                  </p>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}

        {speakers.length > 0 && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-xs text-muted-foreground mb-2">Detected Speakers</p>
            <div className="flex flex-wrap gap-2">
              {speakers.map((speaker) => (
                <Badge key={speaker} variant="outline" className="text-xs">
                  <User className="h-3 w-3 mr-1" />
                  {speaker}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
