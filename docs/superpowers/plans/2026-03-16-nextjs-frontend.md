# Next.js + shadcn/ui Frontend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken Streamlit UI with a Next.js + shadcn/ui frontend that demonstrates the Foreign Whispers dubbing pipeline.

**Architecture:** Next.js 15 App Router frontend in `frontend/`, proxying API calls to the existing FastAPI backend. Single-page split-panel UI: pipeline steps on the left, results on the right. Pre-baked demo video for instant playback, plus live pipeline for other videos.

**Tech Stack:** Next.js 15, TypeScript, shadcn/ui, Tailwind CSS v4, pnpm

**Spec:** `docs/superpowers/specs/2026-03-16-nextjs-frontend-design.md`

---

## File Map

### New files (frontend/)

| File | Responsibility |
|------|---------------|
| `frontend/package.json` | Dependencies, scripts |
| `frontend/next.config.ts` | Standalone output, API proxy rewrites |
| `frontend/components.json` | shadcn/ui configuration |
| `frontend/src/app/layout.tsx` | Root layout, fonts, dark theme |
| `frontend/src/app/page.tsx` | Server component — reads manifest, renders client shell |
| `frontend/src/app/globals.css` | Tailwind @theme + shadcn CSS variables + custom theme |
| `frontend/src/lib/utils.ts` | `cn()` utility (shadcn) + `formatTime()` helper |
| `frontend/src/lib/types.ts` | TypeScript interfaces matching Pydantic schemas |
| `frontend/src/lib/api.ts` | Typed fetch wrappers for FastAPI endpoints |
| `frontend/src/hooks/use-pipeline.ts` | Pipeline state machine + sequential API calls |
| `frontend/src/components/pipeline-page.tsx` | Client component shell (top bar + split panel) |
| `frontend/src/components/video-selector.tsx` | Video dropdown + language select + start button |
| `frontend/src/components/pipeline-tracker.tsx` | Left sidebar — step list with status icons |
| `frontend/src/components/result-panel.tsx` | Right panel — dispatches to step-specific views |
| `frontend/src/components/transcript-view.tsx` | Scrollable timestamped transcript |
| `frontend/src/components/translation-view.tsx` | Side-by-side EN/ES via Tabs |
| `frontend/src/components/audio-player.tsx` | TTS audio playback |
| `frontend/src/components/video-player.tsx` | Final video playback |
| `frontend/public/videos.json` | Video manifest |
| `frontend/Dockerfile` | Multi-stage Node.js build |

### Modified files (backend)

| File | Change |
|------|--------|
| `api/src/routers/tts.py` | Add `GET /api/audio/{video_id}` endpoint (mirrors stitch.py pattern) |

### Modified files (infra)

| File | Change |
|------|--------|
| `docker-compose.yml` | Replace `app` service with `frontend` service |
| `Dockerfile` | Remove `default` stage (Streamlit CMD) |

---

## Chunk 1: Scaffold + Backend Audio Endpoint

### Task 1: Add audio streaming endpoint to FastAPI

**Files:**
- Modify: `api/src/routers/tts.py` (add GET endpoint, mirrors `GET /api/video/{video_id}` in `stitch.py`)

- [ ] **Step 1: Read the existing pattern in stitch.py**

Read `api/src/routers/stitch.py` lines 57-70 to see how `GET /api/video/{video_id}` is implemented. The audio endpoint must follow the same pattern: import `settings` from config, use `title_for_video_id()` to locate the file, return a `FileResponse`.

- [ ] **Step 2: Add the audio endpoint to tts.py**

Add to the end of `api/src/routers/tts.py`:

```python
@router.get("/audio/{video_id}")
async def get_audio(video_id: str):
    audio_dir = pathlib.Path(settings.ui_dir) / "translated_audio"
    title = _tts_service.title_for_video_id(video_id, str(audio_dir))
    if not title:
        raise HTTPException(status_code=404, detail="Audio not found")
    audio_path = audio_dir / f"{title}.wav"
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(audio_path), media_type="audio/wav")
```

Ensure `FileResponse` and `HTTPException` are imported at the top (add if missing).

- [ ] **Step 3: Verify the API starts with the new endpoint**

```bash
cd /home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers && uv run uvicorn api.src.main:app --host 0.0.0.0 --port 8080 &
sleep 5 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/audio/nonexistent
```

Expected: `404` (route exists, file not found). Kill the server after.

- [ ] **Step 4: Commit**

```bash
git add api/src/routers/tts.py
git commit -m "feat(api): add GET /api/audio/{video_id} endpoint for WAV streaming"
```

### Task 2: Scaffold Next.js project with shadcn/ui

**Files:**
- Create: `frontend/` directory with Next.js scaffold
- Create: `frontend/components.json` (via shadcn init)

- [ ] **Step 1: Initialize Next.js project**

```bash
cd /home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers
pnpm dlx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --use-pnpm \
  --import-alias "@/*" \
  --turbopack
```

- [ ] **Step 2: Initialize shadcn/ui**

```bash
cd frontend
pnpm dlx shadcn@latest init --defaults
```

- [ ] **Step 3: Add required shadcn components**

```bash
cd frontend
pnpm dlx shadcn@latest add select button card badge scroll-area tabs skeleton alert separator progress
```

- [ ] **Step 4: Configure next.config.ts with standalone output and API proxy**

Replace `frontend/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL || "http://localhost:8080"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
```

- [ ] **Step 5: Verify the dev server starts**

```bash
cd frontend && pnpm dev
```

Open http://localhost:3000 — should show default Next.js page.

- [ ] **Step 6: Commit**

```bash
cd /home/pantelis.monogioudis/local/ai/apps/computer-vision/auraison-app/foreign-whispers
git add frontend/
git commit -m "feat(frontend): scaffold Next.js 15 + shadcn/ui project"
```

### Task 3: Add TypeScript types and API client

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`

- [ ] **Step 1: Create TypeScript interfaces**

```typescript
// frontend/src/lib/types.ts

export interface Video {
  id: string;
  title: string;
  url: string;
  has_demo: boolean;
  demo_assets?: DemoAssets;
}

export interface DemoAssets {
  transcript_en: string;
  transcript_es: string;
  audio: string;
  video: string;
}

export interface CaptionSegment {
  start: number;
  end: number;
  text: string;
  duration?: number;
}

export interface DownloadResponse {
  video_id: string;
  title: string;
  caption_segments: CaptionSegment[];
}

export interface TranscribeSegment {
  id?: number;
  start: number;
  end: number;
  text: string;
}

export interface TranscribeResponse {
  video_id: string;
  language: string;
  text: string;
  segments: TranscribeSegment[];
}

export interface TranslateResponse {
  video_id: string;
  target_language: string;
  text: string;
  segments: TranscribeSegment[];
}

export interface TTSResponse {
  video_id: string;
  audio_path: string;
}

export interface StitchResponse {
  video_id: string;
  video_path: string;
}

export type PipelineStage = "download" | "transcribe" | "translate" | "tts" | "stitch";
export type StageStatus = "pending" | "active" | "complete" | "error";

export interface StageState {
  status: StageStatus;
  result?: unknown;
  error?: string;
  duration_ms?: number;
}

export interface PipelineState {
  status: "idle" | "running" | "complete" | "error";
  stages: Record<PipelineStage, StageState>;
  selectedStage: PipelineStage;
  videoId?: string;
  isDemo: boolean;
}
```

- [ ] **Step 2: Create API client**

```typescript
// frontend/src/lib/api.ts

import type {
  DownloadResponse,
  TranscribeResponse,
  TranslateResponse,
  TTSResponse,
  StitchResponse,
} from "./types";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new ApiError(res.status, text);
  }
  return res.json();
}

export async function downloadVideo(url: string): Promise<DownloadResponse> {
  return fetchJson<DownloadResponse>("/api/download", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function transcribeVideo(videoId: string): Promise<TranscribeResponse> {
  return fetchJson<TranscribeResponse>(`/api/transcribe/${videoId}`, {
    method: "POST",
  });
}

export async function translateVideo(
  videoId: string,
  targetLanguage = "es"
): Promise<TranslateResponse> {
  return fetchJson<TranslateResponse>(
    `/api/translate/${videoId}?target_language=${targetLanguage}`,
    { method: "POST" }
  );
}

export async function synthesizeSpeech(videoId: string): Promise<TTSResponse> {
  return fetchJson<TTSResponse>(`/api/tts/${videoId}`, {
    method: "POST",
  });
}

export async function stitchVideo(videoId: string): Promise<StitchResponse> {
  return fetchJson<StitchResponse>(`/api/stitch/${videoId}`, {
    method: "POST",
  });
}

export function getVideoUrl(videoId: string): string {
  return `/api/video/${videoId}`;
}

export function getAudioUrl(videoId: string): string {
  return `/api/audio/${videoId}`;
}
```

- [ ] **Step 3: Verify types compile**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat(frontend): add TypeScript types and API client"
```

### Task 4: Create the pipeline state machine hook

**Files:**
- Create: `frontend/src/hooks/use-pipeline.ts`

- [ ] **Step 1: Create the hook**

```typescript
// frontend/src/hooks/use-pipeline.ts
"use client";

import { useCallback, useReducer } from "react";
import type {
  PipelineStage,
  PipelineState,
  StageState,
  Video,
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
  isDemo: false,
};

type Action =
  | { type: "START"; videoId: string }
  | { type: "STAGE_ACTIVE"; stage: PipelineStage }
  | { type: "STAGE_COMPLETE"; stage: PipelineStage; result: unknown; duration_ms: number }
  | { type: "STAGE_ERROR"; stage: PipelineStage; error: string }
  | { type: "SELECT_STAGE"; stage: PipelineStage }
  | { type: "PIPELINE_COMPLETE" }
  | { type: "RESET" }
  | { type: "DEMO_COMPLETE"; results: Record<PipelineStage, unknown>; demoAssets: import("@/lib/types").DemoAssets };

function reducer(state: PipelineState, action: Action): PipelineState {
  switch (action.type) {
    case "RESET":
      return INITIAL_STATE;

    case "START":
      return {
        ...state,
        status: "running",
        videoId: action.videoId,
        stages: initialStages(),
        selectedStage: "download",
        isDemo: false,
      };

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
      };

    case "PIPELINE_COMPLETE":
      return { ...state, status: "complete", selectedStage: "stitch" };

    case "SELECT_STAGE":
      return { ...state, selectedStage: action.stage };

    case "DEMO_COMPLETE": {
      const stages = {} as Record<PipelineStage, StageState>;
      for (const s of STAGES) {
        stages[s] = { status: "complete", result: action.results[s], duration_ms: 0 };
      }
      return {
        ...state,
        status: "complete",
        stages,
        selectedStage: "stitch",
        isDemo: true,
      };
    }

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

  const loadDemo = useCallback(async (video: Video) => {
    if (!video.demo_assets) return;
    const assets = video.demo_assets;
    const [enRes, esRes] = await Promise.all([
      fetch(assets.transcript_en).then((r) => r.json()),
      fetch(assets.transcript_es).then((r) => r.json()),
    ]);
    dispatch({
      type: "DEMO_COMPLETE",
      results: {
        download: { video_id: video.id, title: video.title, caption_segments: [] },
        transcribe: enRes,
        translate: esRes,
        tts: { video_id: video.id, audio_path: assets.audio },
        stitch: { video_id: video.id, video_path: assets.video },
      },
    });
  }, []);

  const runPipeline = useCallback(async (video: Video) => {
    dispatch({ type: "START", videoId: video.id });

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
      await run("tts", () => synthesizeSpeech(dl.video_id));
      await run("stitch", () => stitchVideo(dl.video_id));
      dispatch({ type: "PIPELINE_COMPLETE" });
    } catch {
      // Error already dispatched in run()
    }
  }, []);

  const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  return { state, runPipeline, loadDemo, selectStage, reset };
}
```

- [ ] **Step 2: Verify types compile**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/use-pipeline.ts
git commit -m "feat(frontend): add pipeline state machine hook"
```

---

## Chunk 2: UI Components

### Task 5: Create video manifest and video selector component

**Files:**
- Create: `frontend/public/videos.json`
- Create: `frontend/src/components/video-selector.tsx`

- [ ] **Step 1: Create video manifest**

```json
[
  {
    "id": "7hPDiwJOHl4",
    "title": "Pete Hegseth: The 60 Minutes Interview",
    "url": "https://www.youtube.com/watch?v=7hPDiwJOHl4",
    "has_demo": true,
    "demo_assets": {
      "transcript_en": "/demo/7hPDiwJOHl4/transcript_en.json",
      "transcript_es": "/demo/7hPDiwJOHl4/transcript_es.json",
      "audio": "/demo/7hPDiwJOHl4/audio.wav",
      "video": "/demo/7hPDiwJOHl4/video.mp4"
    }
  },
  {
    "id": "G3Eup4mfJdA",
    "title": "Volodymyr Zelenskyy: The 60 Minutes Interview",
    "url": "https://www.youtube.com/watch?v=G3Eup4mfJdA",
    "has_demo": false
  },
  {
    "id": "480OGItLZNo",
    "title": "Vladimir Putin: The 60 Minutes Interview",
    "url": "https://www.youtube.com/watch?v=480OGItLZNo",
    "has_demo": false
  }
]
```

Save to `frontend/public/videos.json`.

- [ ] **Step 2: Create video selector component**

```tsx
// frontend/src/components/video-selector.tsx
"use client";

import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
        <SelectTrigger className="w-[400px]">
          <SelectValue placeholder="Select a video..." />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {videos.map((v) => (
              <SelectItem key={v.id} value={v.id}>
                <span className="flex items-center gap-2">
                  {v.title}
                  {v.has_demo && (
                    <Badge variant="secondary" className="text-xs">
                      Demo
                    </Badge>
                  )}
                </span>
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
```

- [ ] **Step 3: Verify types compile**

```bash
cd frontend && pnpm tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/public/videos.json frontend/src/components/video-selector.tsx
git commit -m "feat(frontend): add video manifest and selector component"
```

### Task 6: Create pipeline tracker sidebar

**Files:**
- Create: `frontend/src/components/pipeline-tracker.tsx`

- [ ] **Step 1: Create the pipeline tracker component**

```tsx
// frontend/src/components/pipeline-tracker.tsx
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
```

- [ ] **Step 2: Verify types compile**

```bash
cd frontend && pnpm tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/pipeline-tracker.tsx
git commit -m "feat(frontend): add pipeline tracker sidebar component"
```

### Task 7: Create result panel and sub-views

**Files:**
- Create: `frontend/src/components/result-panel.tsx`
- Create: `frontend/src/components/transcript-view.tsx` (uses `formatTime` from `@/lib/utils`)
- Create: `frontend/src/components/translation-view.tsx` (uses `formatTime` from `@/lib/utils`)
- Create: `frontend/src/components/audio-player.tsx`
- Create: `frontend/src/components/video-player.tsx`

- [ ] **Step 1: Create transcript view**

```tsx
// frontend/src/components/transcript-view.tsx
"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { formatTime } from "@/lib/utils";
import type { TranscribeSegment } from "@/lib/types";

interface TranscriptViewProps {
  segments: TranscribeSegment[];
}

export function TranscriptView({ segments }: TranscriptViewProps) {
  return (
    <ScrollArea className="h-[500px]">
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
```

- [ ] **Step 2: Create translation view**

```tsx
// frontend/src/components/translation-view.tsx
"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatTime } from "@/lib/utils";
import type { TranscribeSegment } from "@/lib/types";

interface TranslationViewProps {
  englishSegments: TranscribeSegment[];
  spanishSegments: TranscribeSegment[];
}

export function TranslationView({
  englishSegments,
  spanishSegments,
}: TranslationViewProps) {
  return (
    <Tabs defaultValue="side-by-side">
      <TabsList>
        <TabsTrigger value="side-by-side">Side by Side</TabsTrigger>
        <TabsTrigger value="english">English</TabsTrigger>
        <TabsTrigger value="spanish">Spanish</TabsTrigger>
      </TabsList>

      <TabsContent value="side-by-side">
        <ScrollArea className="h-[500px]">
          <div className="flex flex-col gap-3 pr-4">
            {englishSegments.map((en, i) => {
              const es = spanishSegments[i];
              return (
                <div key={i} className="grid grid-cols-[50px_1fr_1fr] gap-3">
                  <span className="font-mono text-xs text-primary/70">
                    {formatTime(en.start)}
                  </span>
                  <p className="text-sm text-foreground">{en.text}</p>
                  <p className="text-sm text-amber-200/90">{es?.text ?? ""}</p>
                </div>
              );
            })}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="english">
        <ScrollArea className="h-[500px]">
          <div className="flex flex-col gap-2 pr-4">
            {englishSegments.map((seg, i) => (
              <div key={i} className="flex gap-3">
                <span className="font-mono text-xs text-primary/70">
                  {formatTime(seg.start)}
                </span>
                <p className="text-sm">{seg.text}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
      </TabsContent>

      <TabsContent value="spanish">
        <ScrollArea className="h-[500px]">
          <div className="flex flex-col gap-2 pr-4">
            {spanishSegments.map((seg, i) => (
              <div key={i} className="flex gap-3">
                <span className="font-mono text-xs text-primary/70">
                  {formatTime(seg.start)}
                </span>
                <p className="text-sm text-amber-200/90">{seg.text}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
      </TabsContent>
    </Tabs>
  );
}
```

- [ ] **Step 3: Create audio player**

```tsx
// frontend/src/components/audio-player.tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface AudioPlayerProps {
  src: string;
  title?: string;
}

export function AudioPlayer({ src, title = "Synthesized Audio" }: AudioPlayerProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <audio controls className="w-full" src={src}>
          Your browser does not support the audio element.
        </audio>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Create video player**

```tsx
// frontend/src/components/video-player.tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface VideoPlayerProps {
  src: string;
  title?: string;
}

export function VideoPlayer({ src, title = "Dubbed Video" }: VideoPlayerProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <video controls className="w-full rounded-md" src={src}>
          Your browser does not support the video element.
        </video>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 5: Create result panel dispatcher**

```tsx
// frontend/src/components/result-panel.tsx
"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, RotateCcw } from "lucide-react";
import type {
  PipelineState,
  PipelineStage,
  DownloadResponse,
  TranscribeResponse,
  TranslateResponse,
} from "@/lib/types";
import { getAudioUrl, getVideoUrl } from "@/lib/api";
import { TranscriptView } from "./transcript-view";
import { TranslationView } from "./translation-view";
import { AudioPlayer } from "./audio-player";
import { VideoPlayer } from "./video-player";

interface ResultPanelProps {
  state: PipelineState;
  transcribeResult?: TranscribeResponse;
  onRetry?: () => void;
}

export function ResultPanel({ state, transcribeResult, onRetry }: ResultPanelProps) {
  const stage = state.selectedStage;
  const stageState = state.stages[stage];

  if (stageState.status === "pending") {
    return (
      <div className="flex h-[500px] items-center justify-center text-muted-foreground">
        Waiting to start...
      </div>
    );
  }

  if (stageState.status === "active") {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-6 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }

  if (stageState.status === "error") {
    return (
      <Alert variant="destructive">
        <AlertCircle className="size-4" />
        <AlertTitle>Pipeline Error</AlertTitle>
        <AlertDescription className="flex flex-col gap-3">
          <p>{stageState.error}</p>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry} className="w-fit">
              <RotateCcw className="mr-2" />
              Retry
            </Button>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  return <StageResult stage={stage} state={state} transcribeResult={transcribeResult} />;
}

function StageResult({
  stage,
  state,
  transcribeResult,
}: {
  stage: PipelineStage;
  state: PipelineState;
  transcribeResult?: TranscribeResponse;
}) {
  const result = state.stages[stage].result;

  switch (stage) {
    case "download": {
      const dl = result as DownloadResponse;
      return (
        <div className="flex flex-col gap-2">
          <h3 className="text-lg font-semibold">{dl.title}</h3>
          <p className="text-sm text-muted-foreground">
            {dl.caption_segments.length} caption segments detected
          </p>
        </div>
      );
    }

    case "transcribe": {
      const tr = result as TranscribeResponse;
      return <TranscriptView segments={tr.segments} />;
    }

    case "translate": {
      const tl = result as TranslateResponse;
      const enSegments = transcribeResult?.segments ?? [];
      return <TranslationView englishSegments={enSegments} spanishSegments={tl.segments} />;
    }

    case "tts": {
      const videoId = state.videoId!;
      const src = state.isDemo
        ? ((result as { audio_path: string }).audio_path)
        : getAudioUrl(videoId);
      return <AudioPlayer src={src} />;
    }

    case "stitch": {
      const videoId = state.videoId!;
      const src = state.isDemo
        ? ((result as { video_path: string }).video_path)
        : getVideoUrl(videoId);
      return <VideoPlayer src={src} title="Foreign Whispers — Dubbed Video" />;
    }

    default:
      return null;
  }
}
```

- [ ] **Step 6: Verify types compile**

```bash
cd frontend && pnpm tsc --noEmit
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/transcript-view.tsx \
       frontend/src/components/translation-view.tsx \
       frontend/src/components/audio-player.tsx \
       frontend/src/components/video-player.tsx \
       frontend/src/components/result-panel.tsx
git commit -m "feat(frontend): add result panel and sub-view components"
```

### Task 8: Create main page and layout with editorial dark theme

**Files:**
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/globals.css`
- Create: `frontend/src/components/pipeline-page.tsx`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Update globals.css with dark editorial theme**

Replace `frontend/src/app/globals.css`. After `pnpm dlx shadcn@latest init`, the file will have default shadcn CSS variables. Replace the `:root` / `.dark` variable blocks with the editorial dark theme values below. Keep any `@import` or `@tailwind` directives that shadcn generated at the top.

Override the dark theme CSS variables (inside the `.dark` or `:root` selector, depending on what shadcn generated):

```css
--background: 240 10% 6%;
--foreground: 210 20% 93%;
--card: 240 10% 9%;
--card-foreground: 210 20% 93%;
--popover: 240 10% 9%;
--popover-foreground: 210 20% 93%;
--primary: 45 93% 47%;
--primary-foreground: 240 10% 6%;
--secondary: 240 6% 14%;
--secondary-foreground: 210 20% 93%;
--muted: 240 6% 14%;
--muted-foreground: 215 15% 55%;
--accent: 240 6% 14%;
--accent-foreground: 210 20% 93%;
--destructive: 0 84% 60%;
--destructive-foreground: 210 20% 93%;
--border: 240 6% 18%;
--input: 240 6% 18%;
--ring: 45 93% 47%;
```

Also add the serif font variable for headings:

```css
.font-serif {
  font-family: var(--font-serif), Georgia, serif;
}
```

- [ ] **Step 2: Update layout.tsx with fonts and dark class**

```tsx
// frontend/src/app/layout.tsx
import type { Metadata } from "next";
import { DM_Serif_Display, Geist, Geist_Mono } from "next/font/google";
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
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 3: Create pipeline page client component**

```tsx
// frontend/src/components/pipeline-page.tsx
"use client";

import { useState } from "react";
import { Separator } from "@/components/ui/separator";
import type { Video, TranscribeResponse } from "@/lib/types";
import { usePipeline } from "@/hooks/use-pipeline";
import { VideoSelector } from "./video-selector";
import { PipelineTracker } from "./pipeline-tracker";
import { ResultPanel } from "./result-panel";

interface PipelinePageProps {
  videos: Video[];
}

export function PipelinePage({ videos }: PipelinePageProps) {
  const [selectedVideo, setSelectedVideo] = useState<Video | null>(null);
  const { state, runPipeline, loadDemo, selectStage, reset } = usePipeline();

  const handleStart = () => {
    if (!selectedVideo) return;
    if (selectedVideo.has_demo) {
      loadDemo(selectedVideo);
    } else {
      runPipeline(selectedVideo);
    }
  };

  const handleSelectVideo = (video: Video) => {
    setSelectedVideo(video);
    reset();
  };

  const transcribeResult = state.stages.transcribe.result as
    | TranscribeResponse
    | undefined;

  const handleRetry = () => {
    if (selectedVideo) runPipeline(selectedVideo);
  };

  return (
    <div className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="border-b border-border/40 px-8 py-6">
        <h1 className="font-serif text-4xl tracking-tight">Foreign Whispers</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          YouTube video dubbing pipeline — transcribe, translate, dub
        </p>
      </header>

      {/* Controls */}
      <div className="border-b border-border/40 px-8 py-4">
        <VideoSelector
          videos={videos}
          selectedVideo={selectedVideo}
          onSelectVideo={handleSelectVideo}
          onStart={handleStart}
          isRunning={state.status === "running"}
        />
      </div>

      <Separator />

      {/* Split Panel */}
      <div className="flex flex-1 gap-0">
        {/* Left: Pipeline Steps */}
        <aside className="border-r border-border/40 p-4">
          <PipelineTracker state={state} onSelectStage={selectStage} />
        </aside>

        {/* Right: Result Panel */}
        <main className="flex-1 p-6">
          <ResultPanel
            state={state}
            transcribeResult={transcribeResult}
            onRetry={handleRetry}
          />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Update page.tsx as server component**

```tsx
// frontend/src/app/page.tsx
import { readFile } from "fs/promises";
import { join } from "path";
import { PipelinePage } from "@/components/pipeline-page";
import type { Video } from "@/lib/types";

export default async function Home() {
  const data = await readFile(
    join(process.cwd(), "public", "videos.json"),
    "utf-8"
  );
  const videos: Video[] = JSON.parse(data);

  return <PipelinePage videos={videos} />;
}
```

- [ ] **Step 5: Verify production build succeeds**

```bash
cd frontend && pnpm build
```

Expected: Build completes without errors. Produces `.next/standalone/` directory.

- [ ] **Step 6: Verify dev server renders the page**

```bash
cd frontend && pnpm dev
```

Open http://localhost:3000 — should show the "Foreign Whispers" header, video selector dropdown, and empty pipeline tracker.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/layout.tsx \
       frontend/src/app/globals.css \
       frontend/src/app/page.tsx \
       frontend/src/components/pipeline-page.tsx
git commit -m "feat(frontend): wire up main page with editorial dark theme"
```

---

## Chunk 3: Docker Integration

### Task 9: Create frontend Dockerfile

**Files:**
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

```dockerfile
# frontend/Dockerfile
FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM base AS runner
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 2: Add `.dockerignore` for frontend**

```
# frontend/.dockerignore
node_modules
.next
.git
```

Save to `frontend/.dockerignore`.

- [ ] **Step 3: Commit**

```bash
git add frontend/Dockerfile frontend/.dockerignore
git commit -m "feat(frontend): add multi-stage Dockerfile"
```

### Task 10: Update docker-compose.yml — replace Streamlit with Next.js

**Files:**
- Modify: `docker-compose.yml`
- Modify: `Dockerfile` (remove default stage)

- [ ] **Step 1: Remove default stage from root Dockerfile AND update docker-compose.yml atomically**

Both changes must happen together — removing the Dockerfile's `default` stage without updating compose (or vice versa) will break the build.

In `Dockerfile`, remove these lines at the end:

```dockerfile
# ── Default target (used when no --target is specified) ──
FROM cpu AS default
EXPOSE 8501
CMD ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

- [ ] **Step 2: Replace the entire docker-compose.yml**

Replace the full `docker-compose.yml` with the content below. Key changes: `app` service removed, `frontend` service added, `api` gets `target: cpu` (required since `default` stage is gone), `cookies.txt` and transcription data mounts moved to `api`:

```yaml
services:
  # ── STT (Speech-to-Text) ─────────────────────────────────────────────
  whisper:
    container_name: foreign-whispers-stt
    image: ghcr.io/speaches-ai/speaches:latest-cuda-12.6.3
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - whisper-cache:/home/ubuntu/.cache/huggingface/hub
    environment:
      - WHISPER__MODEL=Systran/faster-whisper-medium
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    healthcheck:
      test: ["CMD", "curl", "--fail", "http://0.0.0.0:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  # ── TTS (Text-to-Speech) ─────────────────────────────────────────────
  xtts:
    container_name: foreign-whispers-tts
    build:
      context: https://github.com/widlers/XTTS2-Docker.git
      dockerfile: docker/Dockerfile
    restart: unless-stopped
    shm_size: "8gb"
    ports:
      - "8020:8020"
    environment:
      - COQUI_TOS_AGREED=1
      - USE_CACHE=true
      - STREAM_MODE=false
      - DEVICE=cuda
      - OUTPUT=/app/output
      - SPEAKER=/app/speakers
      - MODEL=/app/xtts_models
    volumes:
      - xtts-models:/app/xtts_models
      - ./data/speakers:/app/speakers
      - xtts-output:/app/output
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

  # ── API (FastAPI backend) ────────────────────────────────────────────
  api:
    container_name: foreign-whispers-api
    build:
      context: .
      dockerfile: Dockerfile
      target: cpu
    restart: unless-stopped
    ports:
      - "8080:8000"
    command: ["uv", "run", "uvicorn", "api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
    environment:
      - XTTS_API_URL=http://xtts:8020
      - FW_WHISPER_MODEL=base
      - FW_TTS_MODEL_NAME=tts_models/es/css10/vits
    volumes:
      - ./ui:/app/ui
      - ./cookies.txt:/app/cookies.txt
      - ./data/transcriptions/en:/app/data/transcriptions/en
      - ./data/transcriptions/es:/app/data/transcriptions/es
    depends_on:
      xtts:
        condition: service_started

  # ── Frontend (Next.js) ──────────────────────────────────────────────
  frontend:
    container_name: foreign-whispers-frontend
    build:
      context: ./frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "8501:3000"
    environment:
      - API_URL=http://api:8000
    depends_on:
      api:
        condition: service_started
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 15s

volumes:
  whisper-cache:
  xtts-models:
  xtts-output:
```

Note: Uses `wget` for healthcheck (available in alpine) instead of `curl`.

- [ ] **Step 3: Verify docker compose config is valid**

```bash
docker compose config --quiet
```

Expected: No errors.

- [ ] **Step 4: Build and start frontend**

```bash
docker compose build frontend api
docker compose up frontend -d
```

Verify at http://localhost:8501.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml Dockerfile
git commit -m "feat(docker): replace Streamlit with Next.js frontend service"
```

### Task 11: Prepare demo assets (placeholder)

**Files:**
- Create: `frontend/public/demo/7hPDiwJOHl4/` directory with placeholder files

- [ ] **Step 1: Create demo asset directories**

```bash
mkdir -p frontend/public/demo/7hPDiwJOHl4
```

- [ ] **Step 2: Create placeholder transcript files for demo**

List available transcripts and pick the first one for the demo:

```bash
ls data/transcriptions/en/ data/transcriptions/es/
```

Copy a specific transcript (use the first available file):

```bash
# Copy a specific English transcript (adjust filename to match what exists)
cp "data/transcriptions/en/$(ls data/transcriptions/en/ | head -1)" frontend/public/demo/7hPDiwJOHl4/transcript_en.json

# Copy a specific Spanish transcript
cp "data/transcriptions/es/$(ls data/transcriptions/es/ | head -1)" frontend/public/demo/7hPDiwJOHl4/transcript_es.json
```

If no transcripts exist, create minimal placeholders:

```bash
echo '{"text":"Good evening.","language":"en","segments":[{"id":0,"start":0,"end":5,"text":"Good evening."}]}' > frontend/public/demo/7hPDiwJOHl4/transcript_en.json
echo '{"text":"Buenas noches.","language":"es","segments":[{"id":0,"start":0,"end":5,"text":"Buenas noches."}]}' > frontend/public/demo/7hPDiwJOHl4/transcript_es.json
```

Note: The actual demo MP4 and WAV must be generated by running the full pipeline once on the selected video. This is a manual step — run the pipeline locally, then copy the outputs to `frontend/public/demo/7hPDiwJOHl4/`. The demo will work with just transcripts (audio/video players will show errors for missing files, which is acceptable for initial development).

- [ ] **Step 3: Commit**

```bash
git add frontend/public/demo/
git commit -m "feat(frontend): add demo asset placeholders"
```

### Task 12: End-to-end verification

- [ ] **Step 1: Start all services**

```bash
docker compose up -d
```

- [ ] **Step 2: Verify frontend loads**

Open http://localhost:8501 — should show the Foreign Whispers UI with dark theme, video selector dropdown, and pipeline tracker.

- [ ] **Step 3: Verify API proxy works**

```bash
curl http://localhost:8501/healthz
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Test demo video selection**

Select "Pete Hegseth: The 60 Minutes Interview" (marked Demo) from the dropdown. Click "Start Pipeline". All steps should show complete instantly with cached results.

- [ ] **Step 5: Commit final state (if any uncommitted changes remain)**

```bash
git status
# Only add specific changed files — do NOT use git add -A
git add docker-compose.yml Dockerfile frontend/
git commit -m "feat: complete Next.js frontend integration"
```
