"use client";

import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import type { Video } from "@/lib/types";
import { usePipeline } from "@/hooks/use-pipeline";
import { useStudioSettings } from "@/hooks/use-studio-settings";
import { MediaLibrary } from "./media-library";
import { VideoCanvas } from "./video-canvas";
import { ControlPanel } from "./control-panel";

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
    <div className="flex h-screen flex-col">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border/40 px-6 py-3">
        <div>
          <h1 className="font-serif text-2xl tracking-tight">Foreign Whispers</h1>
        </div>
        <span className="text-xs text-muted-foreground">Studio</span>
      </header>

      {/* Three-column body */}
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        {/* Left: Media Library */}
        <ResizablePanel defaultSize={15} minSize={12} maxSize={20}>
          <MediaLibrary
            videos={videos}
            selectedVideoId={selectedVideoId}
            onSelectVideo={handleSelectVideo}
            pipelineState={state}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center: Video Canvas */}
        <ResizablePanel defaultSize={55}>
          <VideoCanvas
            pipelineState={state}
            activeVariantId={state.activeVariantId}
            onSelectVariant={selectVariant}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right: Control Panel */}
        <ResizablePanel defaultSize={30} minSize={20} maxSize={35}>
          <ControlPanel
            settings={settings}
            onToggleSetting={toggleSetting}
            pipelineState={state}
            onStartPipeline={handleStartPipeline}
            isRunning={state.status === "running"}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
