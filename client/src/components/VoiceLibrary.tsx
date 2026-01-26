import { useState, useRef } from "react";
import { Library, Play, Pause, ChevronDown, ChevronUp, User, MapPin, Search, Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { LibraryVoice } from "@shared/schema";

interface VoiceLibraryProps {
  voices: LibraryVoice[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  isLoading?: boolean;
}

export function VoiceLibrary({
  voices,
  selectedId,
  onSelect,
  isLoading = false,
}: VoiceLibraryProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [genderFilter, setGenderFilter] = useState<string>("all");
  const [playingId, setPlayingId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const togglePlay = (voice: LibraryVoice, e: React.MouseEvent) => {
    e.stopPropagation();
    
    if (playingId === voice.id) {
      audioRef.current?.pause();
      setPlayingId(null);
    } else {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      audioRef.current = new Audio(voice.audioUrl);
      audioRef.current.onended = () => setPlayingId(null);
      audioRef.current.onerror = () => setPlayingId(null);
      audioRef.current.play().catch(() => setPlayingId(null));
      setPlayingId(voice.id);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const filteredVoices = voices.filter((voice) => {
    const matchesSearch =
      searchQuery === "" ||
      voice.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      voice.location.toLowerCase().includes(searchQuery.toLowerCase()) ||
      voice.language.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesGender =
      genderFilter === "all" || voice.gender === genderFilter;

    return matchesSearch && matchesGender;
  });

  const maleCount = voices.filter((v) => v.gender === "M").length;
  const femaleCount = voices.filter((v) => v.gender === "F").length;

  return (
    <Card>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Library className="h-5 w-5 text-primary" />
                Voice Library
              </CardTitle>
              <CardDescription className="mt-1">
                {voices.length} pre-recorded voices available
              </CardDescription>
            </div>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="icon" data-testid="button-toggle-library">
                {isOpen ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </Button>
            </CollapsibleTrigger>
          </div>
        </CardHeader>

        <CollapsibleContent>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search voices..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                  data-testid="input-search-voices"
                />
              </div>
              <Select value={genderFilter} onValueChange={setGenderFilter}>
                <SelectTrigger className="w-[120px]" data-testid="select-gender-filter">
                  <Filter className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Filter" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All ({voices.length})</SelectItem>
                  <SelectItem value="M">Male ({maleCount})</SelectItem>
                  <SelectItem value="F">Female ({femaleCount})</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {isLoading ? (
              <div className="text-center py-8 text-muted-foreground">
                <div className="animate-pulse">Loading voice library...</div>
              </div>
            ) : filteredVoices.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Library className="h-10 w-10 mx-auto mb-3 opacity-50" />
                <p className="text-sm">No voices match your search</p>
              </div>
            ) : (
              <ScrollArea className="h-[280px]">
                <div className="space-y-2">
                  {filteredVoices.map((voice) => (
                    <div
                      key={voice.id}
                      className={`flex items-center gap-3 p-3 rounded-md border cursor-pointer transition-colors hover-elevate ${
                        selectedId === voice.id
                          ? "border-primary bg-primary/5"
                          : "border-transparent bg-muted/50"
                      }`}
                      onClick={() => onSelect(voice.id)}
                      data-testid={`library-voice-${voice.id}`}
                    >
                      <Button
                        variant="ghost"
                        size="icon"
                        className="shrink-0"
                        onClick={(e) => togglePlay(voice, e)}
                        data-testid={`button-play-library-${voice.id}`}
                      >
                        {playingId === voice.id ? (
                          <Pause className="h-4 w-4" />
                        ) : (
                          <Play className="h-4 w-4" />
                        )}
                      </Button>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="font-medium truncate" data-testid={`text-voice-name-${voice.id}`}>
                            {voice.name}
                          </p>
                          <Badge variant="outline" className="shrink-0">
                            {voice.language}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground mt-1">
                          <span className="flex items-center gap-1">
                            <User className="h-3 w-3" />
                            {voice.gender === "M" ? "Male" : "Female"}, {voice.age}
                          </span>
                          <span className="flex items-center gap-1">
                            <MapPin className="h-3 w-3" />
                            {voice.location.replace(/_/g, " ")}
                          </span>
                          <span>{formatDuration(voice.duration)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}
