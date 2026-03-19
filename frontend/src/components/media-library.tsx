"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Video, PipelineState, VideoVariant } from "@/lib/types";

interface MediaLibraryProps {
  videos: Video[];
  selectedVideoId: string | null;
  onSelectVideo: (videoId: string) => void;
  pipelineState: PipelineState;
}

function getVideoStatus(
  video: Video,
  pipelineState: PipelineState,
  variants: VideoVariant[]
): { label: string; variant: "default" | "secondary" | "destructive" | "outline" } {
  const videoVariants = variants.filter((v) => v.sourceVideoId === video.id);
  const hasComplete = videoVariants.some((v) => v.status === "complete");
  const hasProcessing = videoVariants.some((v) => v.status === "processing");

  if (pipelineState.videoId === video.id && pipelineState.status === "running") {
    return { label: "In progress", variant: "secondary" };
  }
  if (hasProcessing) return { label: "In progress", variant: "secondary" };
  if (hasComplete) return { label: "Complete", variant: "default" };
  return { label: "Not started", variant: "outline" };
}

export function MediaLibrary({
  videos,
  selectedVideoId,
  onSelectVideo,
  pipelineState,
}: MediaLibraryProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border/40 px-3 py-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Video Library
        </span>
      </div>

      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-2 p-2">
          {videos.map((video) => {
            const isActive = video.id === selectedVideoId;
            const status = getVideoStatus(video, pipelineState, pipelineState.variants);
            const variantCount = pipelineState.variants.filter(
              (v) => v.sourceVideoId === video.id && v.status === "complete"
            ).length;

            return (
              <Card
                key={video.id}
                className={`cursor-pointer p-3 transition-colors hover:bg-accent/10 ${
                  isActive ? "border-primary/50 bg-primary/5" : ""
                }`}
                onClick={() => onSelectVideo(video.id)}
              >
                {/* Thumbnail placeholder */}
                <div className="mb-2 flex h-12 items-center justify-center rounded bg-muted">
                  <span className="text-lg text-muted-foreground/40">&#9654;</span>
                </div>

                <div className="truncate text-sm font-medium">{video.title}</div>

                <div className="mt-2 flex items-center gap-2">
                  <Badge variant={status.variant} className="text-[10px]">
                    {status.label}
                  </Badge>
                  {variantCount > 0 && (
                    <Badge variant="outline" className="text-[10px]">
                      {variantCount} variant{variantCount > 1 ? "s" : ""}
                    </Badge>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
