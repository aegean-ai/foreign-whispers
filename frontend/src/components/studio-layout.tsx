"use client";

import type { Video } from "@/lib/types";
import { usePipeline } from "@/hooks/use-pipeline";
import { useStudioSettings } from "@/hooks/use-studio-settings";
import { AppSidebar } from "./app-sidebar";
import { VideoCanvas } from "./video-canvas";
import { ControlPanel } from "./control-panel";
import { Button } from "@/components/ui/button";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import {
  SidebarProvider,
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarTrigger,
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
    <SidebarProvider>
      {/* Left Sidebar — Video Library */}
      <AppSidebar
        videos={videos}
        selectedVideoId={selectedVideoId}
        onSelectVideo={handleSelectVideo}
        pipelineState={state}
      />

      {/* Center — Main Content */}
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator
            orientation="vertical"
            className="mr-2 data-vertical:h-4 data-vertical:self-auto"
          />
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem className="hidden md:block">
                <BreadcrumbPage className="font-serif text-lg">
                  Foreign Whispers
                </BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator className="hidden md:block" />
              <BreadcrumbItem>
                <BreadcrumbPage>
                  {selectedVideo?.title ?? "Select a video"}
                </BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </header>

        <div className="flex flex-1 overflow-hidden">
          {/* Video canvas */}
          <div className="flex-1 overflow-hidden">
            <VideoCanvas
              pipelineState={state}
              activeVariantId={state.activeVariantId}
              onSelectVariant={selectVariant}
            />
          </div>
        </div>
      </SidebarInset>

      {/* Right Sidebar — Controls */}
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
