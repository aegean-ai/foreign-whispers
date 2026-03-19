"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from "@/components/ui/sidebar";
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
    <SidebarGroup>
      <SidebarGroupContent>
        <SidebarMenu>
          {videos.map((video) => {
            const isActive = video.id === selectedVideoId;
            const status = getVideoStatus(video, pipelineState, pipelineState.variants);
            const variantCount = pipelineState.variants.filter(
              (v) => v.sourceVideoId === video.id && v.status === "complete"
            ).length;

            return (
              <SidebarMenuItem key={video.id}>
                <SidebarMenuButton
                  isActive={isActive}
                  onClick={() => onSelectVideo(video.id)}
                  className="h-auto py-2"
                  tooltip={video.title}
                >
                  <div className="flex w-full flex-col gap-1.5">
                    {/* Thumbnail placeholder */}
                    <div className="flex h-10 items-center justify-center rounded bg-sidebar-accent/30">
                      <span className="text-sm text-sidebar-foreground/30">&#9654;</span>
                    </div>

                    <span className="truncate text-xs font-medium group-data-[collapsible=icon]:hidden">
                      {video.title}
                    </span>

                    <div className="flex items-center gap-1.5 group-data-[collapsible=icon]:hidden">
                      <Badge variant={status.variant} className="text-[9px] px-1.5 py-0">
                        {status.label}
                      </Badge>
                      {variantCount > 0 && (
                        <Badge variant="outline" className="text-[9px] px-1.5 py-0">
                          {variantCount}
                        </Badge>
                      )}
                    </div>
                  </div>
                </SidebarMenuButton>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}
