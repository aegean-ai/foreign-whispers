# Studio Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the frontend from a two-panel pipeline view into a three-column studio layout with resizable panels and shadcn/ui accordion controls.

**Architecture:** Replace `pipeline-page.tsx` with a ResizablePanelGroup layout: left media library (video cards), center video canvas, right control panel (accordion groups). Existing result components (transcript, translation, audio, video player) are preserved and embedded in the new layout. State management splits into `use-studio-settings` (control panel) and extended `use-pipeline` (execution + variants).

**Tech Stack:** Next.js 15, React 19, shadcn/ui (Accordion, Checkbox, Resizable, Tooltip, Card, Badge, ScrollArea, Button), Tailwind CSS v4, TypeScript

**Spec:** `docs/superpowers/specs/2026-03-19-studio-layout-design.md`

---

### Task 1: Add types and extend state

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Create: `frontend/src/hooks/use-studio-settings.ts`

- [ ] **Step 1: Add new types to `types.ts`**

Add after the existing `PipelineState` interface (line 66):

```typescript
export interface StudioSettings {
  dubbing: string[];
  diarization: string[];
  voiceCloning: string[];
}

export interface VideoVariant {
  id: string;
  sourceVideoId: string;
  label: string;
  settings: StudioSettings;
  status: "complete" | "processing" | "error";
}

export const DEFAULT_STUDIO_SETTINGS: StudioSettings = {
  dubbing: ["baseline"],
  diarization: [],
  voiceCloning: [],
};
```

- [ ] **Step 2: Create `use-studio-settings.ts`**

```typescript
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
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors related to new files

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/hooks/use-studio-settings.ts
git commit -m "feat(frontend): add StudioSettings types and use-studio-settings hook"
```

---

### Task 2: Update API client

**Files:**
- Modify: `frontend/src/lib/api.ts:51-55`

- [ ] **Step 1: Update `synthesizeSpeech` to accept settings**

Replace lines 51-55:

```typescript
export async function synthesizeSpeech(
  videoId: string,
  settings?: StudioSettings
): Promise<TTSResponse> {
  const params = new URLSearchParams();
  if (settings?.dubbing.includes("aligned")) {
    params.set("alignment", "on");
  }
  if (settings?.diarization.length) {
    params.set("diarization", settings.diarization.join(","));
  }
  if (settings?.voiceCloning.length) {
    params.set("voice_cloning", settings.voiceCloning.join(","));
  }
  const qs = params.toString();
  return fetchJson<TTSResponse>(`/api/tts/${videoId}${qs ? `?${qs}` : ""}`, {
    method: "POST",
  });
}
```

- [ ] **Step 2: Add import for StudioSettings**

Add `StudioSettings` to the import from `"./types"` at line 1.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): add settings params to synthesizeSpeech API call"
```

---

### Task 3: Extend use-pipeline with variants

**Files:**
- Modify: `frontend/src/hooks/use-pipeline.ts`

- [ ] **Step 1: Extend PipelineState in types.ts**

Replace the existing `PipelineState` interface in `frontend/src/lib/types.ts` with:

```typescript
export interface PipelineState {
  status: "idle" | "running" | "complete" | "error";
  stages: Record<PipelineStage, StageState>;
  selectedStage: PipelineStage;
  videoId?: string;
  variants: VideoVariant[];
  activeVariantId?: string;
}
```

- [ ] **Step 2: Update use-pipeline.ts reducer and hook**

Replace the full file content of `frontend/src/hooks/use-pipeline.ts`:

```typescript
"use client";

import { useCallback, useReducer } from "react";
import type {
  PipelineStage,
  PipelineState,
  StageState,
  StudioSettings,
  Video,
  VideoVariant,
} from "@/lib/types";
import {
  downloadVideo,
  transcribeVideo,
  translateVideo,
  synthesizeSpeech,
  stitchVideo,
} from "@/lib/api";

const STAGES: PipelineStage[] = [
  "download",
  "transcribe",
  "translate",
  "tts",
  "stitch",
];

function initialStages(): Record<PipelineStage, StageState> {
  return Object.fromEntries(
    STAGES.map((s) => [s, { status: "pending" as const }])
  ) as Record<PipelineStage, StageState>;
}

const INITIAL_STATE: PipelineState = {
  status: "idle",
  stages: initialStages(),
  selectedStage: "download",
  variants: [],
};

function makeVariantLabel(settings: StudioSettings): string {
  const parts = [
    ...settings.dubbing.map((d) => d.charAt(0).toUpperCase() + d.slice(1)),
    ...settings.diarization,
    ...settings.voiceCloning,
  ];
  return parts.length > 0 ? parts.join(" + ") : "Default";
}

function makeVariantId(videoId: string, settings: StudioSettings): string {
  const key = [
    ...[...settings.dubbing].sort(),
    ...[...settings.diarization].sort(),
    ...[...settings.voiceCloning].sort(),
  ].join("_");
  return `${videoId}_${key || "default"}`;
}

type Action =
  | { type: "START"; videoId: string; settings: StudioSettings }
  | { type: "STAGE_ACTIVE"; stage: PipelineStage }
  | { type: "STAGE_COMPLETE"; stage: PipelineStage; result: unknown; duration_ms: number }
  | { type: "STAGE_ERROR"; stage: PipelineStage; error: string }
  | { type: "SELECT_STAGE"; stage: PipelineStage }
  | { type: "PIPELINE_COMPLETE" }
  | { type: "SELECT_VARIANT"; variantId: string }
  | { type: "RESET" };

function reducer(state: PipelineState, action: Action): PipelineState {
  switch (action.type) {
    case "RESET":
      return INITIAL_STATE;

    case "START": {
      const variantId = makeVariantId(action.videoId, action.settings);
      const variant: VideoVariant = {
        id: variantId,
        sourceVideoId: action.videoId,
        label: makeVariantLabel(action.settings),
        settings: action.settings,
        status: "processing",
      };
      return {
        ...state,
        status: "running",
        videoId: action.videoId,
        stages: initialStages(),
        selectedStage: "download",
        variants: [
          ...state.variants.filter((v) => v.id !== variantId),
          variant,
        ],
        activeVariantId: variantId,
      };
    }

    case "STAGE_ACTIVE":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: { status: "active" },
        },
        selectedStage: action.stage,
      };

    case "STAGE_COMPLETE":
      return {
        ...state,
        stages: {
          ...state.stages,
          [action.stage]: {
            status: "complete",
            result: action.result,
            duration_ms: action.duration_ms,
          },
        },
        selectedStage: action.stage,
      };

    case "STAGE_ERROR":
      return {
        ...state,
        status: "error",
        stages: {
          ...state.stages,
          [action.stage]: { status: "error", error: action.error },
        },
        selectedStage: action.stage,
        variants: state.variants.map((v) =>
          v.id === state.activeVariantId ? { ...v, status: "error" as const } : v
        ),
      };

    case "PIPELINE_COMPLETE":
      return {
        ...state,
        status: "complete",
        selectedStage: "stitch",
        variants: state.variants.map((v) =>
          v.id === state.activeVariantId ? { ...v, status: "complete" as const } : v
        ),
      };

    case "SELECT_STAGE":
      return { ...state, selectedStage: action.stage };

    case "SELECT_VARIANT":
      return { ...state, activeVariantId: action.variantId };

    default:
      return state;
  }
}

export function usePipeline() {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);

  const selectStage = useCallback(
    (stage: PipelineStage) => dispatch({ type: "SELECT_STAGE", stage }),
    []
  );

  const selectVariant = useCallback(
    (variantId: string) => dispatch({ type: "SELECT_VARIANT", variantId }),
    []
  );

  const runPipeline = useCallback(async (video: Video, settings: StudioSettings) => {
    dispatch({ type: "START", videoId: video.id, settings });

    const run = async <T,>(
      stage: PipelineStage,
      fn: () => Promise<T>
    ): Promise<T> => {
      dispatch({ type: "STAGE_ACTIVE", stage });
      const t0 = performance.now();
      try {
        const result = await fn();
        dispatch({
          type: "STAGE_COMPLETE",
          stage,
          result,
          duration_ms: Math.round(performance.now() - t0),
        });
        return result;
      } catch (err) {
        dispatch({
          type: "STAGE_ERROR",
          stage,
          error: err instanceof Error ? err.message : String(err),
        });
        throw err;
      }
    };

    try {
      const dl = await run("download", () => downloadVideo(video.url));
      await run("transcribe", () => transcribeVideo(dl.video_id));
      await run("translate", () => translateVideo(dl.video_id, "es"));
      await run("tts", () => synthesizeSpeech(dl.video_id, settings));
      await run("stitch", () => stitchVideo(dl.video_id));
      dispatch({ type: "PIPELINE_COMPLETE" });
    } catch {
      // Error already dispatched in run()
    }
  }, []);

  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  return { state, runPipeline, selectStage, selectVariant, reset };
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/hooks/use-pipeline.ts
git commit -m "feat(frontend): extend use-pipeline with variant tracking and settings"
```

---

### Task 4: Create accordion control components

**Files:**
- Create: `frontend/src/components/dubbing-method-accordion.tsx`
- Create: `frontend/src/components/diarization-accordion.tsx`
- Create: `frontend/src/components/voice-cloning-accordion.tsx`

- [ ] **Step 1: Create `dubbing-method-accordion.tsx`**

```tsx
"use client";

import { AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Checkbox } from "@/components/ui/checkbox";

interface DubbingMethodAccordionProps {
  selected: string[];
  onToggle: (value: string) => void;
}

const METHODS = [
  { value: "baseline", label: "Baseline", description: "No temporal alignment" },
  { value: "aligned", label: "Aligned", description: "Syllable-based stretch to match original timing" },
];

export function DubbingMethodAccordion({ selected, onToggle }: DubbingMethodAccordionProps) {
  return (
    <AccordionItem value="dubbing-method">
      <AccordionTrigger className="px-3 text-sm">Dubbing Method</AccordionTrigger>
      <AccordionContent className="px-3 pb-3">
        <div className="flex flex-col gap-2">
          {METHODS.map((m) => (
            <label
              key={m.value}
              className="flex cursor-pointer items-center gap-3 rounded-md border border-border/40 p-2 transition-colors hover:bg-accent/10 data-[checked=true]:border-primary/50 data-[checked=true]:bg-primary/5"
              data-checked={selected.includes(m.value)}
            >
              <Checkbox
                checked={selected.includes(m.value)}
                onCheckedChange={() => onToggle(m.value)}
              />
              <div>
                <div className="text-sm font-medium">{m.label}</div>
                <div className="text-xs text-muted-foreground">{m.description}</div>
              </div>
            </label>
          ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}
```

- [ ] **Step 2: Create `diarization-accordion.tsx`**

```tsx
"use client";

import { AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Checkbox } from "@/components/ui/checkbox";

interface DiarizationAccordionProps {
  selected: string[];
  onToggle: (value: string) => void;
}

const METHODS = [
  { value: "pyannote", label: "pyannote", description: "Speaker diarization via pyannote.audio" },
  { value: "whisper-based", label: "Whisper-based", description: "Speaker detection from Whisper timestamps" },
];

export function DiarizationAccordion({ selected, onToggle }: DiarizationAccordionProps) {
  return (
    <AccordionItem value="diarization-methods">
      <AccordionTrigger className="px-3 text-sm">Diarization Methods</AccordionTrigger>
      <AccordionContent className="px-3 pb-3">
        <div className="flex flex-col gap-2">
          {METHODS.map((m) => (
            <label
              key={m.value}
              className="flex cursor-pointer items-center gap-3 rounded-md border border-border/40 p-2 transition-colors hover:bg-accent/10 data-[checked=true]:border-primary/50 data-[checked=true]:bg-primary/5"
              data-checked={selected.includes(m.value)}
            >
              <Checkbox
                checked={selected.includes(m.value)}
                onCheckedChange={() => onToggle(m.value)}
              />
              <div>
                <div className="text-sm font-medium">{m.label}</div>
                <div className="text-xs text-muted-foreground">{m.description}</div>
              </div>
            </label>
          ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}
```

- [ ] **Step 3: Create `voice-cloning-accordion.tsx`**

```tsx
"use client";

import { AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Checkbox } from "@/components/ui/checkbox";

interface VoiceCloningAccordionProps {
  selected: string[];
  onToggle: (value: string) => void;
}

const METHODS = [
  { value: "xtts", label: "XTTS Speaker Embedding", description: "Clone from reference audio via XTTS v2" },
  { value: "openvoice", label: "OpenVoice", description: "Zero-shot voice cloning" },
];

export function VoiceCloningAccordion({ selected, onToggle }: VoiceCloningAccordionProps) {
  return (
    <AccordionItem value="voice-cloning-methods">
      <AccordionTrigger className="px-3 text-sm">Voice Cloning Methods</AccordionTrigger>
      <AccordionContent className="px-3 pb-3">
        <div className="flex flex-col gap-2">
          {METHODS.map((m) => (
            <label
              key={m.value}
              className="flex cursor-pointer items-center gap-3 rounded-md border border-border/40 p-2 transition-colors hover:bg-accent/10 data-[checked=true]:border-primary/50 data-[checked=true]:bg-primary/5"
              data-checked={selected.includes(m.value)}
            >
              <Checkbox
                checked={selected.includes(m.value)}
                onCheckedChange={() => onToggle(m.value)}
              />
              <div>
                <div className="text-sm font-medium">{m.label}</div>
                <div className="text-xs text-muted-foreground">{m.description}</div>
              </div>
            </label>
          ))}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dubbing-method-accordion.tsx frontend/src/components/diarization-accordion.tsx frontend/src/components/voice-cloning-accordion.tsx
git commit -m "feat(frontend): add dubbing, diarization, voice cloning accordion components"
```

---

### Task 5: Create control-panel component

**Files:**
- Create: `frontend/src/components/control-panel.tsx`

- [ ] **Step 1: Create `control-panel.tsx`**

```tsx
"use client";

import { Accordion } from "@/components/ui/accordion";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { DubbingMethodAccordion } from "./dubbing-method-accordion";
import { DiarizationAccordion } from "./diarization-accordion";
import { VoiceCloningAccordion } from "./voice-cloning-accordion";
import { TranscriptView } from "./transcript-view";
import { TranslationView } from "./translation-view";
import { AudioPlayer } from "./audio-player";
import { AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import type { StudioSettings, PipelineState, TranscribeResponse, TranslateResponse } from "@/lib/types";
import { getAudioUrl } from "@/lib/api";

interface ControlPanelProps {
  settings: StudioSettings;
  onToggleSetting: (group: keyof StudioSettings, value: string) => void;
  pipelineState: PipelineState;
  onStartPipeline: () => void;
  isRunning: boolean;
}

export function ControlPanel({
  settings,
  onToggleSetting,
  pipelineState,
  onStartPipeline,
  isRunning,
}: ControlPanelProps) {
  const transcribeResult = pipelineState.stages.transcribe.result as TranscribeResponse | undefined;
  const translateResult = pipelineState.stages.translate.result as TranslateResponse | undefined;
  const ttsComplete = pipelineState.stages.tts.status === "complete";

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border/40 px-3 py-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Controls
        </span>
      </div>

      <ScrollArea className="flex-1">
        <Accordion defaultValue={["dubbing-method"]}>
          <DubbingMethodAccordion
            selected={settings.dubbing}
            onToggle={(v) => onToggleSetting("dubbing", v)}
          />
          <DiarizationAccordion
            selected={settings.diarization}
            onToggle={(v) => onToggleSetting("diarization", v)}
          />
          <VoiceCloningAccordion
            selected={settings.voiceCloning}
            onToggle={(v) => onToggleSetting("voiceCloning", v)}
          />

          {/* Deferred accordion groups (sub-project 2+): Translation, TTS Engine, Alignment, Audio */}

          <AccordionItem value="metrics" disabled>
            <AccordionTrigger className="px-3 text-sm text-muted-foreground italic">
              Metrics
              <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] not-italic">Soon</span>
            </AccordionTrigger>
          </AccordionItem>

          {transcribeResult && (
            <AccordionItem value="transcript">
              <AccordionTrigger className="px-3 text-sm">Transcript</AccordionTrigger>
              <AccordionContent className="px-3 pb-3">
                <TranscriptView segments={transcribeResult.segments} />
              </AccordionContent>
            </AccordionItem>
          )}

          {translateResult && transcribeResult && (
            <AccordionItem value="translation">
              <AccordionTrigger className="px-3 text-sm">Translation</AccordionTrigger>
              <AccordionContent className="px-3 pb-3">
                <TranslationView
                  englishSegments={transcribeResult.segments}
                  spanishSegments={translateResult.segments}
                />
              </AccordionContent>
            </AccordionItem>
          )}

          {ttsComplete && pipelineState.videoId && (
            <AccordionItem value="audio">
              <AccordionTrigger className="px-3 text-sm">Audio</AccordionTrigger>
              <AccordionContent className="px-3 pb-3">
                <AudioPlayer src={getAudioUrl(pipelineState.videoId)} />
              </AccordionContent>
            </AccordionItem>
          )}
        </Accordion>
      </ScrollArea>

      <div className="border-t border-border/40 p-3">
        <Button
          className="w-full"
          onClick={onStartPipeline}
          disabled={isRunning}
        >
          {isRunning ? "Processing..." : "Start Pipeline"}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/control-panel.tsx
git commit -m "feat(frontend): add control panel with accordion groups and start button"
```

---

### Task 6: Create media-library component

**Files:**
- Create: `frontend/src/components/media-library.tsx`

- [ ] **Step 1: Create `media-library.tsx`**

```tsx
"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Video, PipelineState, VideoVariant } from "@/lib/types";

interface MediaLibraryProps {
  videos: Video[];
  selectedVideoId: string | null;
  onSelectVideo: (videoId: string) => void;
  pipelineState: PipelineState;
}

function getVideoStatus(
  video: Video,
  pipelineState: PipelineState,
  variants: VideoVariant[]
): { label: string; variant: "default" | "secondary" | "destructive" | "outline" } {
  const videoVariants = variants.filter((v) => v.sourceVideoId === video.id);
  const hasComplete = videoVariants.some((v) => v.status === "complete");
  const hasProcessing = videoVariants.some((v) => v.status === "processing");

  if (pipelineState.videoId === video.id && pipelineState.status === "running") {
    return { label: "In progress", variant: "secondary" };
  }
  if (hasProcessing) return { label: "In progress", variant: "secondary" };
  if (hasComplete) return { label: "Complete", variant: "default" };
  return { label: "Not started", variant: "outline" };
}

export function MediaLibrary({
  videos,
  selectedVideoId,
  onSelectVideo,
  pipelineState,
}: MediaLibraryProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border/40 px-3 py-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Video Library
        </span>
      </div>

      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-2 p-2">
          {videos.map((video) => {
            const isActive = video.id === selectedVideoId;
            const status = getVideoStatus(video, pipelineState, pipelineState.variants);
            const variantCount = pipelineState.variants.filter(
              (v) => v.sourceVideoId === video.id && v.status === "complete"
            ).length;

            return (
              <Card
                key={video.id}
                className={`cursor-pointer p-3 transition-colors hover:bg-accent/10 ${
                  isActive ? "border-primary/50 bg-primary/5" : ""
                }`}
                onClick={() => onSelectVideo(video.id)}
              >
                {/* Thumbnail placeholder */}
                <div className="mb-2 flex h-12 items-center justify-center rounded bg-muted">
                  <span className="text-lg text-muted-foreground/40">▶</span>
                </div>

                <div className="truncate text-sm font-medium">{video.title}</div>

                <div className="mt-2 flex items-center gap-2">
                  <Badge variant={status.variant} className="text-[10px]">
                    {status.label}
                  </Badge>
                  {variantCount > 0 && (
                    <Badge variant="outline" className="text-[10px]">
                      {variantCount} variant{variantCount > 1 ? "s" : ""}
                    </Badge>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/media-library.tsx
git commit -m "feat(frontend): add media library with video cards and status badges"
```

---

### Task 7: Create video-canvas component

**Files:**
- Create: `frontend/src/components/video-canvas.tsx`

- [ ] **Step 1: Create `video-canvas.tsx`**

```tsx
"use client";

import { Badge } from "@/components/ui/badge";
import type { PipelineState, VideoVariant } from "@/lib/types";
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

  // Determine what to show in the canvas
  const showDubbed = isComplete && activeVariantId !== "original";
  const videoSrc = videoId
    ? showDubbed
      ? getVideoUrl(videoId)
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
            <div className="text-5xl text-muted-foreground/20">▶</div>
            <p className="mt-2 text-sm text-muted-foreground">
              Select a video and run the pipeline
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/video-canvas.tsx
git commit -m "feat(frontend): add video canvas with variant selector strip"
```

---

### Task 8: Create studio-layout and wire everything together

**Files:**
- Create: `frontend/src/components/studio-layout.tsx`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Create `studio-layout.tsx`**

```tsx
"use client";

import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import type { Video } from "@/lib/types";
import { usePipeline } from "@/hooks/use-pipeline";
import { useStudioSettings } from "@/hooks/use-studio-settings";
import { MediaLibrary } from "./media-library";
import { VideoCanvas } from "./video-canvas";
import { ControlPanel } from "./control-panel";

interface StudioLayoutProps {
  videos: Video[];
}

export function StudioLayout({ videos }: StudioLayoutProps) {
  const { selectedVideo, selectedVideoId, settings, toggleSetting, selectVideo } =
    useStudioSettings(videos);
  const { state, runPipeline, selectVariant, reset } = usePipeline();

  const handleStartPipeline = () => {
    if (!selectedVideo) return;
    runPipeline(selectedVideo, settings);
  };

  const handleSelectVideo = (videoId: string) => {
    selectVideo(videoId);
    reset();
  };

  return (
    <div className="flex h-screen flex-col">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border/40 px-6 py-3">
        <div>
          <h1 className="font-serif text-2xl tracking-tight">Foreign Whispers</h1>
        </div>
        <span className="text-xs text-muted-foreground">Studio</span>
      </header>

      {/* Three-column body */}
      <ResizablePanelGroup direction="horizontal" className="flex-1">
        {/* Left: Media Library */}
        <ResizablePanel defaultSize={15} minSize={12} maxSize={20}>
          <MediaLibrary
            videos={videos}
            selectedVideoId={selectedVideoId}
            onSelectVideo={handleSelectVideo}
            pipelineState={state}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center: Video Canvas */}
        <ResizablePanel defaultSize={55}>
          <VideoCanvas
            pipelineState={state}
            activeVariantId={state.activeVariantId}
            onSelectVariant={selectVariant}
          />
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right: Control Panel */}
        <ResizablePanel defaultSize={30} minSize={20} maxSize={35}>
          <ControlPanel
            settings={settings}
            onToggleSetting={toggleSetting}
            pipelineState={state}
            onStartPipeline={handleStartPipeline}
            isRunning={state.status === "running"}
          />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
```

- [ ] **Step 2: Update `page.tsx` to render StudioLayout**

Replace the full content of `frontend/src/app/page.tsx`:

```tsx
import { StudioLayout } from "@/components/studio-layout";
import type { Video } from "@/lib/types";

const API_URL = process.env.API_URL || "http://localhost:8080";

export default async function Home() {
  const res = await fetch(`${API_URL}/api/videos`, { cache: "no-store" });
  const videos: Video[] = res.ok ? await res.json() : [];

  return <StudioLayout videos={videos} />;
}
```

- [ ] **Step 3: Update `layout.tsx` to add TooltipProvider**

Replace the full content of `frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { DM_Serif_Display, Geist, Geist_Mono } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const serif = DM_Serif_Display({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-serif",
});

const geist = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Foreign Whispers",
  description: "YouTube video dubbing pipeline — transcribe, translate, dub",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${serif.variable} ${geist.variable} ${geistMono.variable} min-h-screen bg-background font-sans text-foreground antialiased`}
      >
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 5: Verify dev server starts and page loads**

Run: `cd frontend && pnpm dev &` then open http://localhost:3000 (or whatever port Next.js uses).
Expected: Three-column layout renders. Left panel shows video cards, center shows empty canvas, right shows accordion controls.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/studio-layout.tsx frontend/src/app/page.tsx frontend/src/app/layout.tsx
git commit -m "feat(frontend): wire studio layout — three-column resizable panels"
```

---

### Task 9: Remove old components

**Files:**
- Delete: `frontend/src/components/pipeline-page.tsx`
- Delete: `frontend/src/components/pipeline-tracker.tsx`
- Delete: `frontend/src/components/result-panel.tsx`
- Delete: `frontend/src/components/video-selector.tsx`

- [ ] **Step 1: Verify no imports of old components remain**

Run: `cd frontend && grep -r "pipeline-page\|pipeline-tracker\|result-panel\|video-selector" src/ --include="*.tsx" --include="*.ts" -l`
Expected: No files (page.tsx now imports studio-layout instead)

- [ ] **Step 2: Delete old components**

```bash
rm frontend/src/components/pipeline-page.tsx
rm frontend/src/components/pipeline-tracker.tsx
rm frontend/src/components/result-panel.tsx
rm frontend/src/components/video-selector.tsx
```

- [ ] **Step 3: Verify TypeScript still compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add -u frontend/src/components/
git commit -m "chore(frontend): remove old pipeline-page, tracker, result-panel, video-selector"
```

---

### Task 10: Visual polish and height fixes

**Files:**
- Modify: `frontend/src/components/transcript-view.tsx`
- Modify: `frontend/src/components/translation-view.tsx`

- [ ] **Step 1: Fix ScrollArea heights in transcript and translation views**

The existing components use `h-[500px]` which is too tall for accordion content. Find and replace all occurrences of `h-[500px]` with `max-h-[300px]` in both files:

- `transcript-view.tsx`: search for `h-[500px]` → replace with `max-h-[300px]` (1 occurrence)
- `translation-view.tsx`: search for `h-[500px]` → replace with `max-h-[300px]` (3 occurrences)

- [ ] **Step 2: Verify the app renders correctly**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/transcript-view.tsx frontend/src/components/translation-view.tsx
git commit -m "fix(frontend): reduce ScrollArea heights for accordion embedding"
```
