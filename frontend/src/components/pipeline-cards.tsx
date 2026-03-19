"use client";

import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
  CardAction,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ClockIcon,
  ListIcon,
  LanguagesIcon,
  ActivityIcon,
  FilmIcon,
} from "lucide-react";
import { useElapsed } from "@/hooks/use-elapsed";
import type {
  PipelineState,
  PipelineStage,
  TranscribeResponse,
  TranslateResponse,
  DownloadResponse,
} from "@/lib/types";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function getActiveStageStartedAt(state: PipelineState): number | undefined {
  const stages: PipelineStage[] = ["download", "transcribe", "translate", "tts", "stitch"];
  for (const key of stages) {
    if (state.stages[key].status === "active") return state.stages[key].started_at;
  }
  return undefined;
}

function completedStagesTime(state: PipelineState): number {
  let total = 0;
  for (const stage of Object.values(state.stages)) {
    if (stage.duration_ms) total += stage.duration_ms;
  }
  return total;
}

function pipelineStatusBadge(status: PipelineState["status"]) {
  switch (status) {
    case "running":
      return <Badge variant="secondary">Running</Badge>;
    case "complete":
      return <Badge variant="default">Complete</Badge>;
    case "error":
      return <Badge variant="destructive">Error</Badge>;
    default:
      return <Badge variant="outline">Idle</Badge>;
  }
}

interface PipelineCardsProps {
  pipelineState: PipelineState;
}

export function PipelineCards({ pipelineState }: PipelineCardsProps) {
  const activeElapsed = useElapsed(getActiveStageStartedAt(pipelineState));
  const completedTime = completedStagesTime(pipelineState);
  const totalTime = completedTime + (activeElapsed ?? 0);
  const pipelineTimeStr = totalTime > 0 ? formatDuration(totalTime) : "--";

  const downloadResult = pipelineState.stages.download.result as DownloadResponse | undefined;
  const transcribeResult = pipelineState.stages.transcribe.result as TranscribeResponse | undefined;
  const translateResult = pipelineState.stages.translate.result as TranslateResponse | undefined;

  // Segments count
  const segmentCount = transcribeResult?.segments?.length;

  // Speech duration from transcription segments
  const speechDuration = transcribeResult?.segments?.length
    ? transcribeResult.segments[transcribeResult.segments.length - 1].end
    : undefined;

  // Caption count from download
  const captionCount = downloadResult?.caption_segments?.length;

  // Translation word count
  const translationWordCount = translateResult?.text
    ? translateResult.text.split(/\s+/).filter(Boolean).length
    : undefined;

  // Variants produced
  const variantCount = pipelineState.variants.filter(
    (v) => v.sourceVideoId === pipelineState.videoId
  ).length;

  const metrics: {
    label: string;
    value: string;
    icon: React.ElementType;
    badge?: React.ReactNode;
  }[] = [
    {
      label: "Pipeline",
      value: pipelineTimeStr,
      icon: ClockIcon,
      badge: pipelineStatusBadge(pipelineState.status),
    },
    {
      label: "Segments",
      value: segmentCount != null ? `${segmentCount}` : "--",
      icon: ListIcon,
    },
    {
      label: "Speech Duration",
      value: speechDuration != null ? formatTime(speechDuration) : "--",
      icon: ActivityIcon,
    },
    {
      label: "Translation",
      value: translationWordCount != null ? `${translationWordCount} words` : "--",
      icon: LanguagesIcon,
    },
    {
      label: "Variants",
      value: variantCount > 0 ? `${variantCount}` : "--",
      icon: FilmIcon,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 px-4 lg:px-6 @xl/main:grid-cols-3 @5xl/main:grid-cols-5">
      {metrics.map(({ label, value, icon: Icon, badge }) => (
        <Card key={label} className="@container/card">
          <CardHeader>
            <CardDescription className="flex items-center gap-1.5">
              <Icon className="size-3.5" />
              {label}
            </CardDescription>
            <CardTitle className="text-lg font-semibold tabular-nums">
              {value}
            </CardTitle>
            {badge && <CardAction>{badge}</CardAction>}
          </CardHeader>
        </Card>
      ))}
    </div>
  );
}
