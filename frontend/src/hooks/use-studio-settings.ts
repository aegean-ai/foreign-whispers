"use client";

import { useCallback, useState } from "react";
import type { Video, StudioSettings } from "@/lib/types";
import { DEFAULT_STUDIO_SETTINGS } from "@/lib/types";

export function useStudioSettings(videos: Video[]) {
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(
    videos[0]?.id ?? null
  );
  const [settings, setSettings] = useState<StudioSettings>(DEFAULT_STUDIO_SETTINGS);

  const selectedVideo = videos.find((v) => v.id === selectedVideoId) ?? null;

  const toggleSetting = useCallback(
    (group: keyof StudioSettings, value: string) => {
      setSettings((prev) => {
        const current = prev[group];
        const next = current.includes(value)
          ? current.filter((v) => v !== value)
          : [...current, value];
        return { ...prev, [group]: next };
      });
    },
    []
  );

  const selectVideo = useCallback(
    (videoId: string) => {
      setSelectedVideoId(videoId);
    },
    []
  );

  return { selectedVideo, selectedVideoId, settings, toggleSetting, selectVideo };
}
