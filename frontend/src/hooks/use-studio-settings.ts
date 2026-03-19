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

  // Dubbing is multi-select (baseline + aligned = 2 configs).
  // Diarization and voiceCloning are single-select (radio behavior).
  const SINGLE_SELECT: Set<keyof StudioSettings> = new Set(["dubbing", "diarization", "voiceCloning"]);

  const toggleSetting = useCallback(
    (group: keyof StudioSettings, value: string) => {
      setSettings((prev) => {
        const current = prev[group];
        if (SINGLE_SELECT.has(group)) {
          // Radio: toggle off if already selected, otherwise replace
          const next = current.includes(value) ? [] : [value];
          return { ...prev, [group]: next };
        }
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
