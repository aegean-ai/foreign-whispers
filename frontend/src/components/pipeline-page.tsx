"use client";

import { useState } from "react";
import { Separator } from "@/components/ui/separator";
import type { Video, TranscribeResponse } from "@/lib/types";
import { usePipeline } from "@/hooks/use-pipeline";
import { VideoSelector } from "./video-selector";
import { PipelineTracker } from "./pipeline-tracker";
import { ResultPanel } from "./result-panel";

interface PipelinePageProps {
  videos: Video[];
}

export function PipelinePage({ videos }: PipelinePageProps) {
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);
  const { state, runPipeline, loadDemo, selectStage, reset } = usePipeline();

  const handleStart = () => {
    if (!selectedVideo) return;
    if (selectedVideo.has_demo) {
      loadDemo(selectedVideo);
    } else {
      runPipeline(selectedVideo);
    }
  };

  const handleSelectVideo = (video: Video) => {
    setSelectedVideo(video);
    reset();
  };

  const transcribeResult = state.stages.transcribe.result as
    | TranscribeResponse
    | undefined;

  const handleRetry = () => {
    if (selectedVideo) runPipeline(selectedVideo);
  };

  return (
    <div className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="border-b border-border/40 px-8 py-6">
        <h1 className="font-serif text-4xl tracking-tight">Foreign Whispers</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          YouTube video dubbing pipeline — transcribe, translate, dub
        </p>
      </header>

      {/* Controls */}
      <div className="border-b border-border/40 px-8 py-4">
        <VideoSelector
          videos={videos}
          selectedVideo={selectedVideo}
          onSelectVideo={handleSelectVideo}
          onStart={handleStart}
          isRunning={state.status === "running"}
        />
      </div>

      <Separator />

      {/* Split Panel */}
      <div className="flex flex-1 gap-0">
        {/* Left: Pipeline Steps */}
        <aside className="border-r border-border/40 p-4">
          <PipelineTracker state={state} onSelectStage={selectStage} />
        </aside>

        {/* Right: Result Panel */}
        <main className="flex-1 p-6">
          <ResultPanel
            state={state}
            transcribeResult={transcribeResult}
            onRetry={handleRetry}
          />
        </main>
      </div>
    </div>
  );
}
