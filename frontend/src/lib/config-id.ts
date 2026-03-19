// frontend/src/lib/config-id.ts
import type { StudioSettings } from "./types";

export interface ConfigEntry {
  id: string;
  label: string;
  dubbing?: string;
  diarization?: string;
  voiceCloning?: string;
}

function djb2(str: string): string {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) >>> 0;
  }
  return hash.toString(16).padStart(7, "0").slice(0, 7);
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function canonicalJson(entry: Pick<ConfigEntry, "dubbing" | "diarization" | "voiceCloning">): string {
  const obj: Record<string, string> = {};
  if (entry.dubbing) obj.d = entry.dubbing;
  if (entry.diarization) obj.i = entry.diarization;
  if (entry.voiceCloning) obj.v = entry.voiceCloning;
  return JSON.stringify(obj);
}

export function computeConfigId(entry: Pick<ConfigEntry, "dubbing" | "diarization" | "voiceCloning">): string {
  return "c-" + djb2(canonicalJson(entry));
}

export function computeConfigLabel(entry: Pick<ConfigEntry, "dubbing" | "diarization" | "voiceCloning">): string {
  const parts: string[] = [];
  if (entry.dubbing) parts.push(titleCase(entry.dubbing));
  if (entry.diarization) parts.push(titleCase(entry.diarization));
  if (entry.voiceCloning) parts.push(titleCase(entry.voiceCloning));
  return parts.join(" · ") || "Default";
}

export function computeConfigEntries(settings: StudioSettings): ConfigEntry[] {
  const dubbing = [...new Set(settings.dubbing)];
  const diarization = [...new Set(settings.diarization)];
  const voiceCloning = [...new Set(settings.voiceCloning)];

  // Default to baseline if nothing selected
  if (dubbing.length === 0 && diarization.length === 0 && voiceCloning.length === 0) {
    dubbing.push("baseline");
  }

  // Build axes: only include categories with selections
  const axes: { key: "dubbing" | "diarization" | "voiceCloning"; values: string[] }[] = [];
  if (dubbing.length > 0) axes.push({ key: "dubbing", values: dubbing });
  if (diarization.length > 0) axes.push({ key: "diarization", values: diarization });
  if (voiceCloning.length > 0) axes.push({ key: "voiceCloning", values: voiceCloning });

  // Cartesian product
  let combos: Array<{ dubbing?: string; diarization?: string; voiceCloning?: string }> = [{}];
  for (const axis of axes) {
    const next: typeof combos = [];
    for (const combo of combos) {
      for (const val of axis.values) {
        next.push({ ...combo, [axis.key]: val });
      }
    }
    combos = next;
  }

  return combos.map((combo): ConfigEntry => ({
    ...combo,
    id: computeConfigId(combo),
    label: computeConfigLabel(combo),
  }));
}
