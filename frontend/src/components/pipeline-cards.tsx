"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
  CardAction,
} from "@/components/ui/card";
import {
  DownloadIcon,
  MicIcon,
  LanguagesIcon,
  Volume2Icon,
  ScissorsIcon,
  LoaderIcon,
  CheckCircle2Icon,
  XCircleIcon,
  CircleDashedIcon,
} from "lucide-react";
import type { PipelineStage, PipelineState } from "@/lib/types";

const STAGES: {
  key: PipelineStage;
  label: string;
  icon: React.ElementType;
}[] = [
  { key: "download", label: "Download", icon: DownloadIcon },
  { key: "transcribe", label: "Transcribe", icon: MicIcon },
  { key: "translate", label: "Translate", icon: LanguagesIcon },
  { key: "tts", label: "TTS", icon: Volume2Icon },
  { key: "stitch", label: "Stitch", icon: ScissorsIcon },
];

function statusBadge(status: string) {
  switch (status) {
    case "active":
      return (
        <Badge variant="secondary" className="gap-1">
          <LoaderIcon className="size-3 animate-spin" />
          Running
        </Badge>
      );
    case "complete":
      return (
        <Badge variant="default" className="gap-1">
          <CheckCircle2Icon className="size-3" />
          Done
        </Badge>
      );
    case "error":
      return (
        <Badge variant="destructive" className="gap-1">
          <XCircleIcon className="size-3" />
          Error
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="gap-1">
          <CircleDashedIcon className="size-3" />
          Pending
        </Badge>
      );
  }
}

function formatDuration(ms?: number) {
  if (!ms) return "--";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

interface PipelineCardsProps {
  pipelineState: PipelineState;
}

export function PipelineCards({ pipelineState }: PipelineCardsProps) {
  return (
    <div className="grid grid-cols-2 gap-4 px-4 lg:px-6 @xl/main:grid-cols-3 @5xl/main:grid-cols-5">
      {STAGES.map(({ key, label, icon: Icon }) => {
        const stage = pipelineState.stages[key];
        return (
          <Card key={key} className="@container/card">
            <CardHeader>
              <CardDescription className="flex items-center gap-1.5">
                <Icon className="size-3.5" />
                {label}
              </CardDescription>
              <CardTitle className="text-lg font-semibold tabular-nums">
                {formatDuration(stage.duration_ms)}
              </CardTitle>
              <CardAction>
                {statusBadge(stage.status)}
              </CardAction>
            </CardHeader>
          </Card>
        );
      })}
    </div>
  );
}
