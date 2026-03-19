"use client";

import * as React from "react";
import {
  FilmIcon,
  VideoIcon,
  SettingsIcon,
  PlayIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Accordion } from "@/components/ui/accordion";
import { DubbingMethodAccordion } from "./dubbing-method-accordion";
import { DiarizationAccordion } from "./diarization-accordion";
import { VoiceCloningAccordion } from "./voice-cloning-accordion";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import type { Video, PipelineState, StudioSettings, VideoVariant } from "@/lib/types";

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
  settings: StudioSettings;
  onToggleSetting: (group: keyof StudioSettings, value: string) => void;
  onStartPipeline: () => void;
}

export function AppSidebar({
  videos,
  selectedVideoId,
  onSelectVideo,
  pipelineState,
  settings,
  onToggleSetting,
  onStartPipeline,
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
        {/* Video Library */}
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

        <SidebarSeparator />

        {/* Pipeline Controls */}
        <SidebarGroup>
          <SidebarGroupLabel>
            <SettingsIcon className="size-3.5 mr-1.5" />
            Pipeline Settings
          </SidebarGroupLabel>
          <SidebarGroupContent className="px-2">
            <Accordion multiple defaultValue={["dubbing-method"]}>
              <DubbingMethodAccordion
                selected={settings.dubbing}
                onToggle={(v) => onToggleSetting("dubbing", v)}
              />
              <DiarizationAccordion
                selected={settings.diarization}
                onToggle={(v) => onToggleSetting("diarization", v)}
              />
              <VoiceCloningAccordion
                selected={settings.voiceCloning}
                onToggle={(v) => onToggleSetting("voiceCloning", v)}
              />
            </Accordion>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <Button
          className="w-full"
          onClick={onStartPipeline}
          disabled={pipelineState.status === "running"}
        >
          <PlayIcon className="size-3.5 mr-1.5" />
          {pipelineState.status === "running" ? "Processing..." : "Start Pipeline"}
        </Button>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
