"use client";

import { useElapsed } from "@/hooks/use-elapsed";
import type { PipelineState, PipelineStage } from "@/lib/types";

const STAGE_MESSAGES: Record<PipelineStage, string> = {
  download: "Downloading video and captions from YouTube...",
  transcribe: "Running Whisper large-v3 speech-to-text (this may take a while for long videos)...",
  translate: "Translating English to Spanish via argostranslate...",
  tts: "Synthesizing Spanish speech via XTTS v2...",
  stitch: "Stitching audio, video, and subtitles with ffmpeg...",
};

const STAGE_ORDER: PipelineStage[] = ["download", "transcribe", "translate", "tts", "stitch"];

function formatElapsed(ms: number | undefined): string {
  if (ms == null) return "";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}m ${rem}s`;
}

interface PipelineStatusBarProps {
  pipelineState: PipelineState;
}

export function PipelineStatusBar({ pipelineState }: PipelineStatusBarProps) {
  const activeStage = STAGE_ORDER.find(
    (key) => pipelineState.stages[key].status === "active"
  );
  const startedAt = activeStage ? pipelineState.stages[activeStage].started_at : undefined;
  const elapsed = useElapsed(startedAt);

  if (pipelineState.status === "idle") return null;

  let message: string;
  if (pipelineState.status === "complete") {
    message = "Pipeline complete.";
  } else if (pipelineState.status === "error") {
    const errorStage = STAGE_ORDER.find(
      (key) => pipelineState.stages[key].status === "error"
    );
    const errorMsg = errorStage ? pipelineState.stages[errorStage].error : "Unknown error";
    message = `Error in ${errorStage ?? "pipeline"}: ${errorMsg}`;
  } else if (activeStage) {
    const elapsedStr = formatElapsed(elapsed);
    message = `${STAGE_MESSAGES[activeStage]}${elapsedStr ? ` (${elapsedStr})` : ""}`;
  } else {
    message = "Starting pipeline...";
  }

  return (
    <div className="border-t bg-muted/50 px-4 py-1.5 text-xs text-muted-foreground font-mono truncate lg:px-6">
      {message}
    </div>
  );
}
