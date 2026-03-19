import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { 
  Clock, Play, Pause, Trash2, X, RefreshCw, CheckCircle, AlertCircle, 
  Loader2, Download, ChevronDown, ChevronRight, Volume2, RotateCcw,
  ChevronLeft
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useToast } from "@/hooks/use-toast";
import { apiRequest } from "@/lib/queryClient";
import type { TTSJob, TTSSegmentStatus } from "@shared/schema";

const PAGE_SIZE = 20;

interface JobsResponse {
  jobs: TTSJob[];
  total: number;
  limit: number;
  offset: number;
}

interface JobsPanelProps {
  onPlayAudio?: (url: string) => void;
}

export function JobsPanel({ onPlayAudio }: JobsPanelProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const [playingSegment, setPlayingSegment] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const { data: jobsData, isLoading } = useQuery<JobsResponse>({
    queryKey: ["/api/jobs", { limit: PAGE_SIZE, offset: page * PAGE_SIZE }],
    queryFn: async () => {
      const res = await fetch(`/api/jobs?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to fetch jobs");
      return res.json();
    },
    refetchInterval: (query) => {
      const data = query.state.data as JobsResponse | undefined;
      const hasActiveJob = data?.jobs?.some(j => j.status === "processing" || j.status === "pending");
      return hasActiveJob ? 500 : 2000;
    },
  });

  const jobs = jobsData?.jobs ?? [];
  const totalJobs = jobsData?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalJobs / PAGE_SIZE));

  const hasFinishedJobs = jobs.some(j => 
    j.status === "completed" || j.status === "failed" || j.status === "cancelled"
  );

  const { data: segmentsData } = useQuery<{ segments: TTSSegmentStatus[] }>({
    queryKey: ["/api/jobs", expandedJob, "segments"],
    enabled: !!expandedJob,
    refetchInterval: expandedJob ? 2000 : false,
  });

  const segments = segmentsData?.segments ?? [];

  const invalidateJobs = () => {
    queryClient.invalidateQueries({ queryKey: ["/api/jobs"] });
  };

  const cancelMutation = useMutation({
    mutationFn: async (jobId: string) => {
      await apiRequest("POST", `/api/jobs/${jobId}/cancel`);
    },
    onSuccess: () => {
      invalidateJobs();
      toast({ title: "Job cancelled" });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (jobId: string) => {
      await apiRequest("DELETE", `/api/jobs/${jobId}`);
    },
    onSuccess: () => {
      invalidateJobs();
      toast({ title: "Job deleted" });
    },
  });

  const retryMutation = useMutation({
    mutationFn: async (jobId: string) => {
      await apiRequest("POST", `/api/jobs/${jobId}/retry`);
    },
    onSuccess: () => {
      invalidateJobs();
      toast({ title: "Job retrying", description: "Failed segments will be re-processed." });
    },
    onError: (error: Error) => {
      toast({ title: "Retry failed", description: error.message, variant: "destructive" });
    },
  });

  const clearCompletedMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", "/api/jobs/clear-completed");
      return res.json();
    },
    onSuccess: (data) => {
      invalidateJobs();
      if (page > 0 && jobs.length <= (data.deleted || 0)) {
        setPage(0);
      }
      toast({ title: "Jobs cleared", description: `Removed ${data.deleted} finished job${data.deleted !== 1 ? 's' : ''}.` });
    },
  });

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "pending":
        return <Clock className="h-4 w-4 text-muted-foreground" />;
      case "waiting":
        return <Clock className="h-4 w-4 text-yellow-500" />;
      case "processing":
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed":
        return <AlertCircle className="h-4 w-4 text-destructive" />;
      case "cancelled":
        return <X className="h-4 w-4 text-muted-foreground" />;
      default:
        return null;
    }
  };

  const getStatusBadge = (status: string) => {
    const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
      pending: "secondary",
      waiting: "secondary",
      processing: "default",
      completed: "outline",
      failed: "destructive",
      cancelled: "secondary",
    };
    return (
      <Badge variant={variants[status] || "secondary"} className="text-xs">
        {status}
      </Badge>
    );
  };

  const playSegmentAudio = (jobId: string, segmentId: string) => {
    const url = `/api/jobs/${jobId}/segments/${segmentId}/audio`;
    
    if (audioRef.current) {
      audioRef.current.pause();
    }
    
    audioRef.current = new Audio(url);
    audioRef.current.play();
    setPlayingSegment(segmentId);
    
    audioRef.current.onended = () => {
      setPlayingSegment(null);
    };
  };

  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      setPlayingSegment(null);
    }
  };

  const [downloadingJobId, setDownloadingJobId] = useState<string | null>(null);

  const downloadJobAudio = async (job: TTSJob) => {
    setDownloadingJobId(job.id);
    toast({ title: "Preparing download..." });
    try {
      let url: string;
      if (job.jobType === "export" && job.outputAudioFileId && job.projectId) {
        url = `/api/projects/${job.projectId}/audio/${job.outputAudioFileId}`;
      } else {
        const maxSilenceMs = localStorage.getItem("voxlibris-max-silence-ms") || "300";
        url = `/api/jobs/${job.id}/audio?max_silence_ms=${maxSilenceMs}`;
      }
      const response = await fetch(url, { credentials: "include" });
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      const disposition = response.headers.get("content-disposition");
      const match = disposition?.match(/filename="?(.+?)"?$/);
      a.download = match?.[1] || (job.jobType === "export" ? `export-${job.id}` : `job-${job.id}.wav`);
      a.click();
      URL.revokeObjectURL(blobUrl);
      toast({ title: "Download complete" });
    } catch {
      toast({ title: "Download failed", description: "Could not download audio", variant: "destructive" });
    } finally {
      setDownloadingJobId(null);
    }
  };

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
      }
    };
  }, []);

  return (
    <Card data-testid="jobs-panel">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base flex items-center gap-2">
            <RefreshCw className="h-4 w-4" />
            Generation Jobs
            {totalJobs > 0 && (
              <Badge variant="secondary" className="text-xs ml-1" data-testid="badge-jobs-total">{totalJobs}</Badge>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            {hasFinishedJobs && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => clearCompletedMutation.mutate()}
                disabled={clearCompletedMutation.isPending}
                data-testid="clear-completed-jobs"
                className="text-xs h-7"
              >
                {clearCompletedMutation.isPending ? (
                  <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                ) : (
                  <Trash2 className="h-3 w-3 mr-1" />
                )}
                Clear finished
              </Button>
            )}
            {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {jobs.length === 0 && !isLoading && (
            <div className="text-center py-8 text-muted-foreground" data-testid="text-no-jobs">
              <p className="text-sm">No jobs yet</p>
              <p className="text-xs mt-1">Export a project to see progress here</p>
            </div>
          )}
            {jobs.map((job) => (
              <Collapsible
                key={job.id}
                open={expandedJob === job.id}
                onOpenChange={(open) => setExpandedJob(open ? job.id : null)}
              >
                <div className="border rounded-lg p-3 space-y-2">
                  <CollapsibleTrigger className="w-full" data-testid={`job-expand-${job.id}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {expandedJob === job.id ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                        {getStatusIcon(job.status)}
                        <span className="font-medium text-sm truncate max-w-[150px]">
                          {job.title}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {getStatusBadge(job.status)}
                      </div>
                    </div>
                  </CollapsibleTrigger>

                  <div className="pl-6">
                    {job.status === "waiting" && (
                      <div className="flex items-center gap-2 text-xs text-yellow-600 dark:text-yellow-400 mb-1" data-testid={`job-waiting-${job.id}`}>
                        <Clock className="h-3 w-3" />
                        <span>{job.errorMessage || "Waiting — engine is busy with another job"}</span>
                      </div>
                    )}
                    {job.status === "processing" && job.errorMessage && job.completedSegments === 0 && job.jobType !== "export" && (
                      <div className="flex items-center gap-2 text-xs text-amber-600 dark:text-amber-400 mb-1" data-testid={`job-wakeup-${job.id}`}>
                        <Loader2 className="h-3 w-3 animate-spin" />
                        <span>{job.errorMessage}</span>
                      </div>
                    )}
                    {job.status !== "waiting" && (
                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                      <span>
                        {job.jobType === "export"
                          ? (job.status === "completed"
                              ? "Export ready"
                              : job.errorMessage && job.status === "processing"
                                ? job.errorMessage
                                : job.totalSegments > 0
                                  ? "Preparing..."
                                  : "Preparing...")
                          : `${job.completedSegments}/${job.totalSegments} segments`
                        }
                      </span>
                      <span>{Math.round(job.progress)}%</span>
                    </div>
                    )}
                    {job.status !== "waiting" && (
                    <Progress value={job.progress} className="h-1.5" />
                    )}
                  </div>

                  <div className="flex items-center gap-1 pl-6">
                    {job.status === "completed" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => downloadJobAudio(job)}
                        disabled={downloadingJobId === job.id}
                        data-testid={`job-download-${job.id}`}
                      >
                        {downloadingJobId === job.id ? (
                          <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                        ) : (
                          <Download className="h-3.5 w-3.5 mr-1" />
                        )}
                        {downloadingJobId === job.id ? "Downloading..." : "Download"}
                      </Button>
                    )}
                    {(job.status === "failed" || job.status === "cancelled") && job.jobType !== "export" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => retryMutation.mutate(job.id)}
                        disabled={retryMutation.isPending}
                        data-testid={`job-retry-${job.id}`}
                      >
                        <RotateCcw className="h-3.5 w-3.5 mr-1" />
                        Retry
                      </Button>
                    )}
                    {(job.status === "processing" || job.status === "waiting") && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => cancelMutation.mutate(job.id)}
                        disabled={cancelMutation.isPending}
                        data-testid={`job-cancel-${job.id}`}
                      >
                        <X className="h-3.5 w-3.5 mr-1" />
                        Cancel
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteMutation.mutate(job.id);
                      }}
                      disabled={deleteMutation.isPending}
                      data-testid={`job-delete-${job.id}`}
                    >
                      <Trash2 className="h-3.5 w-3.5 mr-1" />
                      Delete
                    </Button>
                  </div>

                  <CollapsibleContent>
                    {job.jobType !== "export" && (
                    <div className="mt-3 pt-3 border-t space-y-1.5 pl-6">
                      <div className="text-xs font-medium text-muted-foreground mb-2">
                        Segments:
                      </div>
                      {segments.map((seg) => (
                        <div
                          key={seg.id}
                          className="flex items-center justify-between text-xs py-1.5 px-2 rounded bg-muted/50"
                          data-testid={`segment-${seg.id}`}
                        >
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            {getStatusIcon(seg.status)}
                            <span className="truncate flex-1">
                              {seg.segmentIndex + 1}. {seg.text.slice(0, 50)}...
                            </span>
                          </div>
                          {seg.hasAudio && (
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-6 w-6"
                              onClick={() =>
                                playingSegment === seg.id
                                  ? stopAudio()
                                  : playSegmentAudio(job.id, seg.id)
                              }
                              data-testid={`segment-play-${seg.id}`}
                            >
                              {playingSegment === seg.id ? (
                                <Pause className="h-3 w-3" />
                              ) : (
                                <Volume2 className="h-3 w-3" />
                              )}
                            </Button>
                          )}
                        </div>
                      ))}
                      {segments.length === 0 && (
                        <div className="text-xs text-muted-foreground py-2">
                          No segments yet
                        </div>
                      )}
                    </div>
                    )}
                    {job.jobType === "export" && (
                      <div className="mt-3 pt-3 border-t pl-6">
                        <div className="text-xs text-muted-foreground">
                          {job.exportFormat && <span>Format: {job.exportFormat.toUpperCase()}</span>}
                          {job.errorMessage && job.status === "failed" && (
                            <p className="text-destructive mt-1">{job.errorMessage}</p>
                          )}
                        </div>
                      </div>
                    )}
                  </CollapsibleContent>
                </div>
              </Collapsible>
            ))}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between pt-3 mt-3 border-t">
            <span className="text-xs text-muted-foreground" data-testid="text-jobs-count">
              {totalJobs} job{totalJobs !== 1 ? "s" : ""} total
            </span>
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="outline"
                className="h-7 w-7 p-0"
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                data-testid="button-jobs-prev-page"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="text-xs px-2" data-testid="text-jobs-page">
                {page + 1} / {totalPages}
              </span>
              <Button
                size="sm"
                variant="outline"
                className="h-7 w-7 p-0"
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                data-testid="button-jobs-next-page"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
