"use client";

import * as React from "react";
import { FilmIcon, VideoIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import type { Video, PipelineState, VideoVariant } from "@/lib/types";

function getVideoStatus(
  video: Video,
  pipelineState: PipelineState,
  variants: VideoVariant[]
): { label: string; variant: "default" | "secondary" | "destructive" | "outline" } {
  const videoVariants = variants.filter((v) => v.sourceVideoId === video.id);
  const hasComplete = videoVariants.some((v) => v.status === "complete");
  const hasProcessing = videoVariants.some((v) => v.status === "processing");

  if (pipelineState.videoId === video.id && pipelineState.status === "running") {
    return { label: "Running", variant: "secondary" };
  }
  if (hasProcessing) return { label: "Running", variant: "secondary" };
  if (hasComplete) return { label: "Done", variant: "default" };
  return { label: "New", variant: "outline" };
}

interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  videos: Video[];
  selectedVideoId: string | null;
  onSelectVideo: (videoId: string) => void;
  pipelineState: PipelineState;
}

export function AppSidebar({
  videos,
  selectedVideoId,
  onSelectVideo,
  pipelineState,
  ...props
}: AppSidebarProps) {
  return (
    <Sidebar {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<div />}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <FilmIcon className="size-4" />
              </div>
              <div className="flex flex-col gap-0.5 leading-none">
                <span className="font-semibold">Foreign Whispers</span>
                <span className="text-xs">Dubbing Studio</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Video Library</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {videos.map((video) => {
                const isActive = video.id === selectedVideoId;
                const status = getVideoStatus(video, pipelineState, pipelineState.variants);

                return (
                  <SidebarMenuItem key={video.id}>
                    <SidebarMenuButton
                      isActive={isActive}
                      onClick={() => onSelectVideo(video.id)}
                      tooltip={video.title}
                    >
                      <VideoIcon />
                      <span>{video.title}</span>
                    </SidebarMenuButton>
                    <SidebarMenuBadge>
                      <Badge variant={status.variant} className="text-[9px] px-1 py-0 leading-tight">
                        {status.label}
                      </Badge>
                    </SidebarMenuBadge>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}
