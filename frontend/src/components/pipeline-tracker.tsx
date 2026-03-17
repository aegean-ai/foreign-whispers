"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Circle, XCircle } from "lucide-react";
import type { PipelineStage, PipelineState, StageStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGE_LABELS: Record<PipelineStage, string> = {
  download: "Download",
  transcribe: "Transcribe",
  translate: "Translate",
  tts: "Synthesize Speech",
  stitch: "Render Dubbed Video",
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
            <CardContent className="flex flex-col gap-2 p-3">
              <div className="flex items-center gap-3">
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
                {stageState.status === "active" && (
                  <ElapsedBadge />
                )}
              </div>
              {stageState.status === "active" && (
                <ProgressBar stage={stage} />
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

/** Live elapsed-time counter shown while a stage is running. */
function ElapsedBadge() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t0 = Date.now();
    const id = setInterval(() => setElapsed(Date.now() - t0), 200);
    return () => clearInterval(id);
  }, []);
  return (
    <Badge variant="outline" className="text-xs tabular-nums text-amber-500">
      {(elapsed / 1000).toFixed(1)}s
    </Badge>
  );
}

/** Estimated durations per stage (seconds). Used for the indeterminate progress bar. */
const STAGE_ESTIMATES: Record<PipelineStage, number> = {
  download: 15,
  transcribe: 20,
  translate: 5,
  tts: 180,
  stitch: 600,
};

/** Animated progress bar that fills toward ~90% over the estimated duration. */
function ProgressBar({ stage }: { stage: PipelineStage }) {
  const [pct, setPct] = useState(0);
  const estimate = STAGE_ESTIMATES[stage];

  useEffect(() => {
    const t0 = Date.now();
    const id = setInterval(() => {
      const elapsed = (Date.now() - t0) / 1000;
      // Asymptotic curve: approaches 90% at estimate, never reaches 100%
      const progress = 90 * (1 - Math.exp(-1.5 * elapsed / estimate));
      setPct(Math.min(progress, 95));
    }, 300);
    return () => clearInterval(id);
  }, [estimate]);

  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
      <div
        className="h-full rounded-full bg-amber-500 transition-[width] duration-300 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function StageIcon({ status }: { status: StageStatus }) {
  switch (status) {
    case "complete":
      return <CheckCircle2 className="size-5 text-green-500" />;
    case "active":
      return <div className="size-5 rounded-full border-2 border-amber-500 bg-amber-500/20" />;
    case "error":
      return <XCircle className="size-5 text-destructive" />;
    default:
      return <Circle className="size-5 text-muted-foreground/40" />;
  }
}
