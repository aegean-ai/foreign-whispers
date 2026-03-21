"use client";

import { useCallback, useState } from "react";
import type { Video } from "@/lib/types";
import { usePipeline } from "@/hooks/use-pipeline";
import { useStudioSettingsContext } from "@/contexts/studio-settings-context";
import { AppSidebar } from "./app-sidebar";
import { PipelineCards } from "./pipeline-cards";
import { PipelineStatusBar } from "./pipeline-status-bar";
import { PipelineTable } from "./pipeline-table";
import { VideoCanvas } from "./video-canvas";
import { Separator } from "@/components/ui/separator";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";

interface StudioLayoutProps {
  videos: Video[];
}

export function StudioLayout({ videos }: StudioLayoutProps) {
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(
    videos[0]?.id ?? null
  );
  const selectedVideo = videos.find((v) => v.id === selectedVideoId) ?? null;
  const { settings } = useStudioSettingsContext();
  const { state, runPipeline, selectVariant, reset } = usePipeline();

  const handleStartPipeline = () => {
    if (!selectedVideo) return;
    runPipeline(selectedVideo, settings);
  };

  const handleSelectVideo = useCallback((videoId: string) => {
    setSelectedVideoId(videoId);
    reset();
  }, [reset]);

  return (
    <SidebarProvider
      style={
        {
          "--sidebar-width": "calc(var(--spacing) * 72)",
          "--header-height": "calc(var(--spacing) * 12)",
        } as React.CSSProperties
      }
    >
      <AppSidebar
        variant="inset"
        videos={videos}
        selectedVideoId={selectedVideoId}
        onSelectVideo={handleSelectVideo}
        pipelineState={state}
        onStartPipeline={handleStartPipeline}
      />
      <SidebarInset>
        {/* Site header */}
        <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
          <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
            <SidebarTrigger className="-ml-1" />
            <Separator
              orientation="vertical"
              className="mx-2 h-4 data-vertical:self-auto"
            />
            <h1 className="text-base font-medium">
              {selectedVideo?.title ?? "Select a video"}
            </h1>
          </div>
        </header>

        {/* Main content */}
        <div className="flex flex-1 flex-col">
          <div className="@container/main flex flex-1 flex-col gap-2">
            <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
              <PipelineCards pipelineState={state} />
              <div className="px-4 lg:px-6">
                <VideoCanvas
                  pipelineState={state}
                  activeVariantId={state.activeVariantId}
                  onSelectVariant={selectVariant}
                />
              </div>
              <PipelineTable pipelineState={state} settings={settings} />
            </div>
          </div>
        </div>

        <PipelineStatusBar pipelineState={state} />
      </SidebarInset>
    </SidebarProvider>
  );
}
