"use client";

import type { Video } from "@/lib/types";
import { usePipeline } from "@/hooks/use-pipeline";
import { useStudioSettings } from "@/hooks/use-studio-settings";
import { MediaLibrary } from "./media-library";
import { VideoCanvas } from "./video-canvas";
import { ControlPanel } from "./control-panel";
import { Button } from "@/components/ui/button";
import {
  SidebarProvider,
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarFooter,
  SidebarInset,
  SidebarRail,
} from "@/components/ui/sidebar";

interface StudioLayoutProps {
  videos: Video[];
}

export function StudioLayout({ videos }: StudioLayoutProps) {
  const { selectedVideo, selectedVideoId, settings, toggleSetting, selectVideo } =
    useStudioSettings(videos);
  const { state, runPipeline, selectVariant, reset } = usePipeline();

  const handleStartPipeline = () => {
    if (!selectedVideo) return;
    runPipeline(selectedVideo, settings);
  };

  const handleSelectVideo = (videoId: string) => {
    selectVideo(videoId);
    reset();
  };

  return (
    <SidebarProvider
      defaultOpen
      style={
        {
          "--sidebar-width": "16rem",
          "--sidebar-width-icon": "3rem",
        } as React.CSSProperties
      }
    >
      {/* Left Sidebar — Media Library */}
      <Sidebar side="left" variant="sidebar" collapsible="icon">
        <SidebarHeader className="border-b border-sidebar-border px-3 py-3">
          <span className="text-xs font-medium uppercase tracking-wider text-sidebar-foreground/60 group-data-[collapsible=icon]:hidden">
            Video Library
          </span>
        </SidebarHeader>
        <SidebarContent>
          <MediaLibrary
            videos={videos}
            selectedVideoId={selectedVideoId}
            onSelectVideo={handleSelectVideo}
            pipelineState={state}
          />
        </SidebarContent>
        <SidebarRail />
      </Sidebar>

      {/* Center — Video Canvas */}
      <SidebarInset className="flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between border-b border-border/40 px-6 py-3">
          <h1 className="font-serif text-2xl tracking-tight">Foreign Whispers</h1>
          <span className="text-xs text-muted-foreground">Studio</span>
        </header>

        <div className="flex-1 overflow-hidden">
          <VideoCanvas
            pipelineState={state}
            activeVariantId={state.activeVariantId}
            onSelectVariant={selectVariant}
          />
        </div>
      </SidebarInset>

      {/* Right Sidebar — Control Panel */}
      <Sidebar side="right" variant="sidebar" collapsible="none">
        <SidebarHeader className="border-b border-sidebar-border px-3 py-3">
          <span className="text-xs font-medium uppercase tracking-wider text-sidebar-foreground/60">
            Controls
          </span>
        </SidebarHeader>
        <SidebarContent>
          <ControlPanel
            settings={settings}
            onToggleSetting={toggleSetting}
            pipelineState={state}
          />
        </SidebarContent>
        <SidebarFooter>
          <Button
            className="w-full"
            onClick={handleStartPipeline}
            disabled={state.status === "running"}
          >
            {state.status === "running" ? "Processing..." : "Start Pipeline"}
          </Button>
        </SidebarFooter>
      </Sidebar>
    </SidebarProvider>
  );
}
