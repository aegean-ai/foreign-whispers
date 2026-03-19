"use client";

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DownloadIcon,
  MicIcon,
  LanguagesIcon,
  Volume2Icon,
  ScissorsIcon,
} from "lucide-react";
import type { PipelineStage, PipelineState, StudioSettings } from "@/lib/types";

const STAGES: {
  key: PipelineStage;
  label: string;
  icon: React.ElementType;
  description: string;
}[] = [
  { key: "download", label: "Download", icon: DownloadIcon, description: "Fetch video + captions from YouTube" },
  { key: "transcribe", label: "Transcribe", icon: MicIcon, description: "Speech-to-text via Whisper" },
  { key: "translate", label: "Translate", icon: LanguagesIcon, description: "English to Spanish translation" },
  { key: "tts", label: "TTS", icon: Volume2Icon, description: "Text-to-speech synthesis" },
  { key: "stitch", label: "Stitch", icon: ScissorsIcon, description: "Combine audio + video + subtitles" },
];

function statusBadge(status: string) {
  switch (status) {
    case "active":
      return <Badge variant="secondary">Running</Badge>;
    case "complete":
      return <Badge variant="default">Done</Badge>;
    case "error":
      return <Badge variant="destructive">Error</Badge>;
    default:
      return <Badge variant="outline">Pending</Badge>;
  }
}

interface PipelineTableProps {
  pipelineState: PipelineState;
  settings: StudioSettings;
}

export function PipelineTable({ pipelineState, settings }: PipelineTableProps) {
  function getConfig(stage: PipelineStage): string {
    switch (stage) {
      case "download":
        return pipelineState.videoId ?? "--";
      case "transcribe":
        return "Whisper large-v3";
      case "translate":
        return "argostranslate (en → es)";
      case "tts": {
        const parts: string[] = [];
        if (settings.dubbing.includes("aligned")) parts.push("Aligned");
        else parts.push("Baseline");
        if (settings.voiceCloning.length > 0) parts.push(settings.voiceCloning.join(", "));
        if (settings.diarization.length > 0) parts.push(settings.diarization.join(", "));
        return parts.join(" + ") || "XTTS v2";
      }
      case "stitch":
        return "ffmpeg + moviepy";
      default:
        return "--";
    }
  }

  return (
    <div className="px-4 lg:px-6">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[180px]">Stage</TableHead>
            <TableHead>Description</TableHead>
            <TableHead className="w-[100px]">Status</TableHead>
            <TableHead className="w-[100px] text-right">Duration</TableHead>
            <TableHead>Configuration</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {STAGES.map(({ key, label, icon: Icon, description }) => {
            const stage = pipelineState.stages[key];
            const duration = stage.duration_ms
              ? stage.duration_ms < 1000
                ? `${stage.duration_ms}ms`
                : `${(stage.duration_ms / 1000).toFixed(1)}s`
              : "--";

            return (
              <TableRow key={key}>
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    <Icon className="size-4 text-muted-foreground" />
                    {label}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">{description}</TableCell>
                <TableCell>{statusBadge(stage.status)}</TableCell>
                <TableCell className="text-right tabular-nums">{duration}</TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {getConfig(key)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
