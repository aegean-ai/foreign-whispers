"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, RotateCcw } from "lucide-react";
import type {
  PipelineState,
  PipelineStage,
  DownloadResponse,
  TranscribeResponse,
  TranslateResponse,
} from "@/lib/types";
import { getAudioUrl, getVideoUrl } from "@/lib/api";
import { TranscriptView } from "./transcript-view";
import { TranslationView } from "./translation-view";
import { AudioPlayer } from "./audio-player";
import { VideoPlayer } from "./video-player";

interface ResultPanelProps {
  state: PipelineState;
  transcribeResult?: TranscribeResponse;
  onRetry?: () => void;
}

export function ResultPanel({ state, transcribeResult, onRetry }: ResultPanelProps) {
  const stage = state.selectedStage;
  const stageState = state.stages[stage];

  if (stageState.status === "pending") {
    return (
      <div className="flex h-[500px] items-center justify-center text-muted-foreground">
        Waiting to start...
      </div>
    );
  }

  if (stageState.status === "active") {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  if (stageState.status === "error") {
    return (
      <Alert variant="destructive">
        <AlertCircle className="size-4" />
        <AlertTitle>Pipeline Error</AlertTitle>
        <AlertDescription className="flex flex-col gap-3">
          <p>{stageState.error}</p>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry} className="w-fit">
              <RotateCcw className="mr-2" />
              Retry
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  return <StageResult stage={stage} state={state} transcribeResult={transcribeResult} />;
}

function StageResult({
  stage,
  state,
  transcribeResult,
}: {
  stage: PipelineStage;
  state: PipelineState;
  transcribeResult?: TranscribeResponse;
}) {
  const result = state.stages[stage].result;

  switch (stage) {
    case "download": {
      const dl = result as DownloadResponse;
      return (
        <div className="flex flex-col gap-2">
          <h3 className="text-lg font-semibold">{dl.title}</h3>
          <p className="text-sm text-muted-foreground">
            {dl.caption_segments.length} caption segments detected
          </p>
        </div>
      );
    }

    case "transcribe": {
      const tr = result as TranscribeResponse;
      return <TranscriptView segments={tr.segments} />;
    }

    case "translate": {
      const tl = result as TranslateResponse;
      const enSegments = transcribeResult?.segments ?? [];
      return <TranslationView englishSegments={enSegments} spanishSegments={tl.segments} />;
    }

    case "tts": {
      const videoId = state.videoId!;
      const src = state.isDemo
        ? ((result as { audio_path: string }).audio_path)
        : getAudioUrl(videoId);
      return <AudioPlayer src={src} />;
    }

    case "stitch": {
      const videoId = state.videoId!;
      const src = state.isDemo
        ? ((result as { video_path: string }).video_path)
        : getVideoUrl(videoId);
      return <VideoPlayer src={src} title="Foreign Whispers — Dubbed Video" />;
    }

    default:
      return null;
  }
}
