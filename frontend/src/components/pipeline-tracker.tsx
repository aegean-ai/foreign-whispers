"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { PipelineStage, PipelineState, StageStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGE_LABELS: Record<PipelineStage, string> = {
  download: "Download",
  transcribe: "Transcribe",
  translate: "Translate",
  tts: "Synthesize Speech",
  stitch: "Stitch Video",
};

const STAGE_ORDER: PipelineStage[] = [
  "download",
  "transcribe",
  "translate",
  "tts",
  "stitch",
];

interface PipelineTrackerProps {
  state: PipelineState;
  onSelectStage: (stage: PipelineStage) => void;
}

export function PipelineTracker({ state, onSelectStage }: PipelineTrackerProps) {
  return (
    <div className="flex w-[260px] flex-col gap-1">
      {STAGE_ORDER.map((stage) => {
        const stageState = state.stages[stage];
        const isSelected = state.selectedStage === stage;
        const isClickable = stageState.status === "complete" || stageState.status === "error";

        return (
          <Card
            key={stage}
            className={cn(
              "cursor-default border-transparent transition-colors",
              isSelected && "border-primary/50 bg-accent",
              isClickable && "cursor-pointer hover:bg-accent",
              stageState.status === "pending" && "opacity-50",
              stageState.status === "error" && "border-destructive/50"
            )}
            onClick={() => isClickable && onSelectStage(stage)}
          >
            <CardContent className="flex items-center gap-3 p-3">
              <StageIcon status={stageState.status} />
              <div className="flex flex-1 flex-col">
                <span className="text-sm font-medium">{STAGE_LABELS[stage]}</span>
                {stageState.status === "error" && (
                  <span className="text-xs text-destructive">Failed</span>
                )}
              </div>
              {stageState.status === "complete" && stageState.duration_ms !== undefined && (
                <Badge variant="outline" className="text-xs text-muted-foreground">
                  {(stageState.duration_ms / 1000).toFixed(1)}s
                </Badge>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function StageIcon({ status }: { status: StageStatus }) {
  switch (status) {
    case "complete":
      return <CheckCircle2 className="text-green-500" />;
    case "active":
      return <Loader2 className="animate-spin text-amber-500" />;
    case "error":
      return <XCircle className="text-destructive" />;
    default:
      return <Circle className="text-muted-foreground/40" />;
  }
}
