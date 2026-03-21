"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import type { StudioSettings } from "@/lib/types";
import { DEFAULT_STUDIO_SETTINGS } from "@/lib/types";

type ArraySettingKey = {
  [K in keyof StudioSettings]: StudioSettings[K] extends string[] ? K : never;
}[keyof StudioSettings];

interface StudioSettingsContextValue {
  settings: StudioSettings;
  toggleSetting: (group: ArraySettingKey, value: string) => void;
  toggleUseYoutubeCaptions: () => void;
}

const StudioSettingsContext = createContext<StudioSettingsContextValue | null>(null);

const SINGLE_SELECT: Set<ArraySettingKey> = new Set([
  "diarization",
  "voiceCloning",
] as ArraySettingKey[]);

export function StudioSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<StudioSettings>(DEFAULT_STUDIO_SETTINGS);

  const toggleSetting = useCallback((group: ArraySettingKey, value: string) => {
    setSettings((prev) => {
      const current = prev[group];
      if (SINGLE_SELECT.has(group)) {
        const next = current.includes(value) ? [] : [value];
        return { ...prev, [group]: next };
      }
      const next = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      return { ...prev, [group]: next };
    });
  }, []);

  const toggleUseYoutubeCaptions = useCallback(() => {
    setSettings((prev) => ({ ...prev, useYoutubeCaptions: !prev.useYoutubeCaptions }));
  }, []);

  return (
    <StudioSettingsContext.Provider value={{ settings, toggleSetting, toggleUseYoutubeCaptions }}>
      {children}
    </StudioSettingsContext.Provider>
  );
}

export function useStudioSettingsContext() {
  const ctx = useContext(StudioSettingsContext);
  if (!ctx) throw new Error("useStudioSettingsContext must be used within StudioSettingsProvider");
  return ctx;
}
