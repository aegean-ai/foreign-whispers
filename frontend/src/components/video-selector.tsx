"use client";

import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Loader2, Play } from "lucide-react";
import type { Video } from "@/lib/types";
import { cn } from "@/lib/utils";

interface VideoSelectorProps {
  videos: Video[];
  selectedVideo: Video | null;
  onSelectVideo: (video: Video) => void;
  onStart: () => void;
  isRunning: boolean;
}

export function VideoSelector({
  videos,
  selectedVideo,
  onSelectVideo,
  onStart,
  isRunning,
}: VideoSelectorProps) {
  return (
    <div className="flex items-center gap-4">
      <Select
        value={selectedVideo?.id ?? ""}
        onValueChange={(id) => {
          const video = videos.find((v) => v.id === id);
          if (video) onSelectVideo(video);
        }}
      >
        <SelectTrigger className="w-[400px] text-foreground">
          {selectedVideo ? selectedVideo.title : "Select a video..."}
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {videos.map((v) => (
              <SelectItem key={v.id} value={v.id}>
                {v.title}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>

      <Button
        onClick={onStart}
        disabled={!selectedVideo || isRunning}
        className={cn(
          "min-w-[160px]",
          isRunning && "cursor-not-allowed"
        )}
      >
        {isRunning ? (
          <>
            <Loader2 className="mr-2 animate-spin" />
            Processing...
          </>
        ) : (
          <>
            <Play className="mr-2" />
            Start Pipeline
          </>
        )}
      </Button>
    </div>
  );
}
