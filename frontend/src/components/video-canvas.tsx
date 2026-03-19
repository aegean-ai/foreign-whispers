"use client";

import { Badge } from "@/components/ui/badge";
import type { PipelineState } from "@/lib/types";
import {
  getVideoUrl,
  getOriginalVideoUrl,
  getCaptionsUrl,
  getOriginalCaptionsUrl,
} from "@/lib/api";

interface VideoCanvasProps {
  pipelineState: PipelineState;
  activeVariantId?: string;
  onSelectVariant: (variantId: string) => void;
}

export function VideoCanvas({
  pipelineState,
  activeVariantId,
  onSelectVariant,
}: VideoCanvasProps) {
  const { videoId, variants, status } = pipelineState;
  const isComplete = status === "complete";
  const videoVariants = variants.filter(
    (v) => v.sourceVideoId === videoId && v.status === "complete"
  );

  const activeVariant = variants.find((v) => v.id === activeVariantId);
  const configId = activeVariant?.configId ?? "";

  // Determine what to show in the canvas
  const showDubbed = isComplete && activeVariantId !== "original";
  const videoSrc = videoId
    ? showDubbed && configId
      ? getVideoUrl(videoId, configId)
      : getOriginalVideoUrl(videoId)
    : undefined;
  const captionsSrc = videoId
    ? showDubbed
      ? getCaptionsUrl(videoId)
      : getOriginalCaptionsUrl(videoId)
    : undefined;

  return (
    <div className="flex h-full flex-col bg-background/50">
      {/* Variant selector strip */}
      {videoId && (
        <div className="flex items-center gap-2 border-b border-border/40 px-4 py-2">
          <Badge
            variant={!activeVariantId || activeVariantId === "original" ? "default" : "outline"}
            className="cursor-pointer text-xs"
            onClick={() => onSelectVariant("original")}
          >
            Original
          </Badge>
          {videoVariants.map((v) => (
            <Badge
              key={v.id}
              variant={activeVariantId === v.id ? "default" : "outline"}
              className="cursor-pointer text-xs"
              onClick={() => onSelectVariant(v.id)}
            >
              {v.label}
            </Badge>
          ))}
        </div>
      )}

      {/* Video viewport */}
      <div className="flex flex-1 items-center justify-center p-6">
        {videoSrc ? (
          <video
            controls
            className="max-h-full w-full max-w-full rounded-lg"
            src={videoSrc}
            crossOrigin="anonymous"
            key={videoSrc}
          >
            {captionsSrc && (
              <track
                kind="subtitles"
                src={captionsSrc}
                srcLang="es"
                label="Spanish"
                default
              />
            )}
          </video>
        ) : (
          <div className="text-center">
            <div className="text-5xl text-muted-foreground/20">&#9654;</div>
            <p className="mt-2 text-sm text-muted-foreground">
              Select a video and run the pipeline
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
