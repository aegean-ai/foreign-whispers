# Next.js + shadcn/ui Frontend for Foreign Whispers

**Date:** 2026-03-16
**Status:** Draft
**Issue:** fw-42s

## Problem

The Streamlit frontend is broken (pytube dead, yt-dlp n-challenge requires JS runtime, HF Spaces deployment failed). Students need a polished demo UI for their 30-second pitch video. The existing FastAPI backend has all the endpoints needed — we just need a modern frontend.

## Design Decisions

- **Audience:** Students demonstrating their dubbing pipeline in a pitch video
- **Layout:** Single-page split panel — pipeline steps on the left, results on the right
- **Download approach:** Hybrid — one pre-baked demo video for instant playback, 10 pre-existing transcripts for live pipeline runs. No live YouTube download in the demo (yt-dlp bot detection is unreliable). The download API endpoint remains for local dev.
- **Pipeline progress:** Client-side polling — frontend calls existing API endpoints sequentially
- **Replaces Streamlit:** The `app` service in docker-compose.yml is replaced by a `frontend` service

## Architecture

```
Browser :8501 → frontend (Next.js) :3000 → api (FastAPI) :8000 (host :8080)
                                              ↓
                                    whisper :8000 (host :8000) / xtts :8020 (host :8020)
```

Next.js rewrites `/api/*` → FastAPI backend. No CORS needed — all requests proxied through Next.js.

### API Endpoints Used

**Existing (no changes):**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/download` | Download video + captions (takes `{url}` body) |
| POST | `/api/transcribe/{video_id}` | Whisper transcription |
| POST | `/api/translate/{video_id}?target_language=es` | Argos translation |
| POST | `/api/tts/{video_id}` | TTS synthesis |
| POST | `/api/stitch/{video_id}` | Video composition |
| GET | `/api/video/{video_id}` | Stream final MP4 |

**New (minimal backend additions):**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/audio/{video_id}` | Stream synthesized WAV (needed for `<audio>` player) |

The TTS endpoint returns `{"audio_path": "..."}` (a server-side path). The frontend cannot use this directly — it needs a streaming endpoint analogous to `GET /api/video/{video_id}`.

### Pipeline Flow by Video Type

**Demo video (`has_demo: true`):** All steps show "complete" instantly. Results loaded from static assets in `frontend/public/demo/`. No API calls.

**Non-demo videos (`has_demo: false`):** The video manifest includes the YouTube `url` for each video. The frontend calls:
1. `POST /api/download` with `{url}` — the backend skips re-download if files exist on disk
2. `POST /api/transcribe/{video_id}` — skips if cached
3. `POST /api/translate/{video_id}` — skips if cached
4. `POST /api/tts/{video_id}` — skips if cached
5. `POST /api/stitch/{video_id}` — skips if cached

Each endpoint is idempotent (returns cached result if already processed). The download step may fail if yt-dlp can't reach YouTube — the error is shown and the user can retry or switch to the demo video.

## UI Structure

### Top Bar

App title "Foreign Whispers" with project subtitle. Distinctive display typography.

### Video Selector

- Dropdown (`Select`) of pre-loaded videos from a `videos.json` manifest
- Language selector (`Select`) — Spanish only (TTS model is Spanish; French translation works but TTS/stitch cannot produce French audio)
- "Start Pipeline" button
- One video marked `has_demo: true` shows instant cached results (no API calls)

### Split Panel (main area)

**Left sidebar (~250px):** 5 pipeline steps stacked vertically. Each step shows:
- Status icon: pending (empty circle), active (pulsing dot), done (checkmark), error (X)
- Step name
- Timing when complete
- Clicking a completed step selects it for the right panel

**Right panel (flex-1):** Shows result of the selected step:

| Step | Right Panel Content |
|------|-------------------|
| Download | Video title, caption segment count (`caption_segments.length`) |
| Transcribe | Scrollable timestamped transcript (English) |
| Translate | Side-by-side English/Spanish segments via `Tabs` |
| TTS | Audio player (`<audio>`) via `GET /api/audio/{video_id}` |
| Stitch | Video player (`<video>`) via `GET /api/video/{video_id}` |

When pipeline finishes, auto-switches to final video with hero state.

### Error Handling

Failed step turns red with error message in right panel. "Retry" button re-runs that step.

### Timeouts

Next.js rewrite proxy timeout set to 300s (matches FastAPI backend timeout for Whisper/TTS). If a step exceeds this, the error is shown with a retry option. No user-initiated cancellation — simplicity for a demo UI.

## Pre-loaded Content

### Demo Video (fully processed)

One short 60 Minutes clip (~30-60 seconds), fully pre-baked:
- English transcript JSON
- Spanish translated JSON
- TTS audio WAV
- Final dubbed MP4

**Size budget:** Clip should be under 60 seconds to keep assets small (~5MB MP4, ~2MB WAV). Stored in `frontend/public/demo/` for static serving.

### Video Manifest

`frontend/public/videos.json`:

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
    "title": "...",
    "url": "https://www.youtube.com/watch?v=G3Eup4mfJdA",
    "has_demo": false
  }
]
```

## Tech Stack

- **Next.js 15** (App Router, `output: "standalone"`) with TypeScript
- **shadcn/ui** components via CLI (`pnpm dlx shadcn@latest`)
- **Tailwind CSS v4** (CSS-first config via `@theme`, no `tailwind.config.ts`)
- **pnpm** package manager
- Frontend lives in `frontend/` directory

### shadcn/ui Components

Installed via `pnpm dlx shadcn@latest add`:

| Need | Component |
|------|-----------|
| Video selector | `Select` (`SelectGroup` + `SelectItem`) |
| Start/Retry actions | `Button` with variants |
| Pipeline step cards | `Card` (full composition) |
| Step status | `Badge` with semantic variants |
| Transcript display | `ScrollArea` |
| English/Spanish toggle | `Tabs` (`TabsList` + `TabsTrigger` + `TabsContent`) |
| Loading states | `Skeleton` + `Loader2` icon with `animate-spin` |
| Error feedback | `Alert` |
| Dividers | `Separator` |
| Progress | `Progress` |

### shadcn/ui Rules

- `gap-*` not `space-y-*` for spacing
- Semantic colors (`bg-primary`, `text-muted-foreground`), never raw Tailwind values
- `cn()` for conditional classes
- Icons as children in `Button`: `<Button><Icon className="mr-2" />Label</Button>`
- Full `Card` composition (`CardHeader`/`CardTitle`/`CardDescription`/`CardContent`)
- `"use client"` on components with `useState`/`useEffect`
- Items always inside their Group (`SelectItem` → `SelectGroup`)

### Aesthetic Direction

**Tone:** Editorial/cinematic — production studio control panel feel.

- **Dark theme** — dark slate/zinc backgrounds, high-contrast text
- **Typography:** Distinctive display font for headings (e.g., DM Serif Display), Geist for body (shadcn default)
- **Color accent:** Warm amber/gold for active states (broadcast feel), green for completed, muted for pending
- **Motion:** Subtle — pulse animation on active step, slide-in for result panels via CSS transitions
- **Differentiator:** The split-panel pipeline tracker with real-time stage transitions

No generic AI aesthetics: no Inter/Roboto, no purple gradients on white, no cookie-cutter layouts.

## Pipeline State Machine

The `use-pipeline` hook manages a state machine:

```
idle → downloading → transcribing → translating → synthesizing → stitching → complete
  ↑         |              |              |              |              |
  └─────────┴──────────────┴──────────────┴──────────────┴──────────────┘
                                    (error → retry returns to failed step)
```

**State shape:**

```typescript
type PipelineStage = 'download' | 'transcribe' | 'translate' | 'tts' | 'stitch';
type StageStatus = 'pending' | 'active' | 'complete' | 'error';

interface PipelineState {
  status: 'idle' | 'running' | 'complete' | 'error';
  stages: Record<PipelineStage, {
    status: StageStatus;
    result?: unknown;
    error?: string;
    duration_ms?: number;
  }>;
  selectedStage: PipelineStage;
  videoId?: string;
}
```

## TypeScript Types

`src/lib/types.ts` — matches FastAPI Pydantic schemas:

```typescript
interface Video {
  id: string;
  title: string;
  url: string;
  has_demo: boolean;
  demo_assets?: DemoAssets;
}

interface DemoAssets {
  transcript_en: string;
  transcript_es: string;
  audio: string;
  video: string;
}

interface DownloadResponse {
  video_id: string;
  title: string;
  caption_segments: CaptionSegment[];
}

interface CaptionSegment {
  start: number;
  end: number;
  text: string;
  duration?: number;
}

interface TranscribeResponse {
  video_id: string;
  language: string;
  text: string;
  segments: TranscribeSegment[];
}

interface TranscribeSegment {
  id?: number;
  start: number;
  end: number;
  text: string;
}

interface TranslateResponse {
  video_id: string;
  target_language: string;
  text: string;
  segments: TranscribeSegment[];
}

interface TTSResponse {
  video_id: string;
  audio_path: string;
}

interface StitchResponse {
  video_id: string;
  video_path: string;
}
```

## Docker Changes

### New: `frontend/Dockerfile`

Multi-stage Node.js build with standalone output:

```dockerfile
FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

FROM base AS runner
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

Requires `output: "standalone"` in `next.config.ts` for the `.next/standalone` directory to be produced.

### docker-compose.yml Changes

- **Remove** `app` service (Streamlit)
- **Add** `frontend` service:

```yaml
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
    test: ["CMD", "curl", "-f", "http://localhost:3000"]
    interval: 15s
    timeout: 5s
    retries: 3
    start_period: 15s
```

- **Move** `cookies.txt` mount to `api` service (download happens server-side)

### Existing Dockerfile

Remove the `default` stage (Streamlit CMD). Keep `base`, `cpu`, `gpu` stages for the API.

### next.config.ts

Rewrites to proxy API calls. `localhost:8080` is the local dev fallback (host-mapped port); in Docker, `API_URL=http://api:8000` is set via environment.

```typescript
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.API_URL || 'http://localhost:8080'}/api/:path*`,
      },
    ];
  },
};
```

## File Structure

```
frontend/
├── Dockerfile
├── package.json
├── pnpm-lock.yaml
├── next.config.ts
├── components.json           (shadcn config)
├── public/
│   ├── videos.json           (video manifest)
│   └── demo/                 (pre-baked demo assets, <10MB total)
│       └── {video_id}/
│           ├── transcript_en.json
│           ├── transcript_es.json
│           ├── audio.wav
│           └── video.mp4
├── src/
│   ├── app/
│   │   ├── layout.tsx        (root layout, fonts, dark theme)
│   │   ├── page.tsx          (server component — fetches manifest, renders client shell)
│   │   └── globals.css       (tailwind @theme + shadcn CSS variables)
│   ├── components/
│   │   ├── ui/               (shadcn components — CLI managed)
│   │   ├── pipeline-tracker.tsx   (left sidebar — step list)
│   │   ├── result-panel.tsx       (right panel — step results)
│   │   ├── video-selector.tsx     (top bar dropdown + controls)
│   │   ├── transcript-view.tsx    (scrollable timestamped text)
│   │   ├── translation-view.tsx   (side-by-side EN/ES tabs)
│   │   ├── audio-player.tsx       (TTS audio playback)
│   │   └── video-player.tsx       (final video playback)
│   ├── hooks/
│   │   └── use-pipeline.ts        (pipeline state machine + sequential API calls)
│   └── lib/
│       ├── utils.ts               (cn() — shadcn utility)
│       ├── types.ts               (TypeScript interfaces matching Pydantic schemas)
│       └── api.ts                 (typed fetch wrappers for FastAPI endpoints)
```

`page.tsx` is a server component that reads the video manifest and passes it as props to the client component tree. All pipeline state and interactivity is client-side (`"use client"` components).

## Backend Addition Required

**One new endpoint:** `GET /api/audio/{video_id}` — returns a `FileResponse` streaming the synthesized WAV from `ui/translated_audio/`. Mirrors the existing `GET /api/video/{video_id}` pattern. Add to `api/src/routers/tts.py`.

## Out of Scope

- User authentication
- Multiple concurrent pipelines
- Language pack management UI
- Database/S3 integration in frontend
- French TTS/stitch (translation works, but TTS model is Spanish-only)
- User-initiated pipeline cancellation
- Live YouTube URL text input (unreliable due to bot detection; videos come from manifest)
