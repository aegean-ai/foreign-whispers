"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { formatTime } from "@/lib/utils";
import type { TranscribeSegment } from "@/lib/types";

interface TranscriptViewProps {
  segments: TranscribeSegment[];
}

export function TranscriptView({ segments }: TranscriptViewProps) {
  return (
    <ScrollArea className="max-h-[300px]">
      <div className="flex flex-col gap-2 pr-4">
        {segments.map((seg, i) => (
          <div key={i} className="flex gap-3">
            <span className="shrink-0 font-mono text-xs text-primary/70">
              {formatTime(seg.start)}
            </span>
            <p className="text-sm text-foreground">{seg.text}</p>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
