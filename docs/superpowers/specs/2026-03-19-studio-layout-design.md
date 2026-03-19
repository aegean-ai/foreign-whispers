# Studio Layout Design: Three-Column Layout Shell

**Date**: 2026-03-19
**Issue**: fw-4jc (sub-project 1 of 5)
**Status**: Approved

## Decision

Restructure the Foreign Whispers frontend from a two-panel pipeline view into a three-column studio layout with resizable panels, using shadcn/ui components throughout.

## Context

The current frontend has a fixed two-panel layout: a 260px left sidebar (pipeline tracker with 5 stage icons) and a main content area (result panel that swaps between transcript, translation, audio, and video views per stage). This layout doesn't scale to support dubbing method selection, before/after comparison, diarization, voice cloning, metrics, or multi-variant outputs.

The studio layout follows the professional NLE pattern (DaVinci Resolve, Premiere): a dedicated video viewport in the center, an asset library on the left, and a dense controls panel on the right.

## Sub-project Scope

This is sub-project 1 of 5 for fw-4jc:

1. **Three-column layout shell** (this spec)
2. Right panel controls + dubbing method selector
3. Before/after video comparison
4. Bottom process queue drawer
5. Polish (Cmd+K, export dialog, tooltips, theme refinements)

## Layout Architecture

### Panel Structure

Uses shadcn `ResizablePanelGroup` (flex-based, percentage sizing) — not CSS Grid. The top bar is a separate div above the panel group.

```
Row 1: Top bar (title) — fixed height
Row 2: ResizablePanelGroup direction="horizontal"
  ├── ResizablePanel (left)   defaultSize={15} minSize={12} maxSize={20}
  ├── ResizableHandle
  ├── ResizablePanel (center) defaultSize={55}
  ├── ResizableHandle
  └── ResizablePanel (right)  defaultSize={30} minSize={20} maxSize={35}
```

Approximate pixel equivalents at 1440px viewport: left ~216px, center ~792px, right ~432px.

- Minimum layout width: 1024px (desktop studio tool, no mobile responsive breakpoints)

### Left Sidebar — Media Library

- Persistent list of all videos from `video_registry.yml` as thumbnail cards
- Each card shows: thumbnail placeholder, title, pipeline status badge (Not started / In progress / Complete)
- Pipeline status and variant data are **ephemeral (React state only)** — reset on page refresh. This is a known limitation; persistence (via API or localStorage) is deferred to a future sub-project.
- Active video highlighted with indigo border
- Variant count badge when a source video has multiple pipeline outputs
- "Start Pipeline" button at bottom of the **right panel** (control panel), next to the settings it acts on
- shadcn components: Card, Badge, ScrollArea, Button

### Center — Video Canvas

- Dedicated video viewport (original or dubbed)
- Variant selector strip above video — labeled chips: `Original`, `Baseline`, `Baseline + Aligned`, etc.
- Playback controls below video
- Future: before/after split view (sub-project 3)
- shadcn components: Badge (variant chips)

### Right Panel — Control Panel

Accordion-based, all using shadcn Accordion with Checkbox items and Tooltip hints.

**Top-level accordion groups (in order):**

1. **Dubbing Method** — checkboxes: Baseline, Aligned
2. **Diarization Methods** — checkboxes: pyannote, Whisper-based
3. **Voice Cloning Methods** — checkboxes: XTTS Speaker Embedding, OpenVoice
4. **Translation** — language pair selector (future content)
5. **TTS Engine** — model selector (future content)
6. **Alignment** — stretch clamp sliders (future content)
7. **Audio** — denoising, gain (future content)
8. **Transcript** — renders existing `transcript-view.tsx`
9. **Translation Results** — renders existing `translation-view.tsx`
10. **Metrics** — placeholder, labeled "Soon"

shadcn components: Accordion, Checkbox, Tooltip, ScrollArea

## Multi-Variant Output Model

A single source video can produce multiple dubbed outputs, each tagged with the settings that produced it.

```typescript
interface VideoVariant {
  id: string              // e.g., "abc123_baseline_aligned"
  sourceVideoId: string   // the original video
  label: string           // "Baseline + Aligned" (auto-generated from settings)
  settings: {
    dubbing: string[]     // ["baseline", "aligned"]
    diarization: string[] // []
    voiceCloning: string[] // []
  }
  status: "complete" | "processing" | "error"
}
```

- Video cards in the media library show the source video with a variant count badge
- Center canvas shows a variant selector strip (chips) when a source video has variants
- Clicking a chip switches the video/audio in the canvas
- This feeds naturally into before/after comparison (sub-project 3): pick two variants to compare

## State Management

### Existing: `use-pipeline.ts`

Kept for pipeline execution (download → transcribe → translate → tts → stitch). Extended with:

**New `runPipeline` signature:**
```typescript
runPipeline(video: Video, settings: StudioSettings): void
```

**Extended `PipelineState`:**
```typescript
interface PipelineState {
  status: "idle" | "running" | "complete" | "error"
  stages: Record<PipelineStage, StageState>
  selectedStage: PipelineStage
  videoId?: string
  // New fields:
  variants: VideoVariant[]           // all completed/in-progress variants
  activeVariantId?: string           // which variant is displayed in canvas
}
```

**New reducer actions:**
- `VARIANT_STARTED` — add a new variant with `status: "processing"`
- `VARIANT_COMPLETE` — update variant status, store output paths
- `VARIANT_ERROR` — mark variant as failed
- `SELECT_VARIANT` — switch canvas to a different variant

### New: `use-studio-settings.ts`

Manages control panel state:
- `selectedVideoId` — which video card is active
- `dubbingMethod` — `{ baseline: boolean, aligned: boolean }`
- `diarizationMethod` — `{ pyannote: boolean, whisperBased: boolean }`
- `voiceCloning` — `{ xtts: boolean, openvoice: boolean }`

Settings are passed to the pipeline hook when "Start Pipeline" is clicked.

### API Change

`synthesizeSpeech(videoId)` → `synthesizeSpeech(videoId, settings: StudioSettings)`

```typescript
interface StudioSettings {
  dubbing: string[]      // ["baseline", "aligned"]
  diarization: string[]  // ["pyannote"]
  voiceCloning: string[] // []
}
```

The TTS endpoint receives settings as query params. Backend sets `FW_ALIGNMENT` and other flags accordingly.

## Component File Structure

### Create

| File | Responsibility | shadcn Components |
|---|---|---|
| `src/components/studio-layout.tsx` | Root layout shell, CSS Grid | ResizablePanelGroup, ResizablePanel, ResizableHandle |
| `src/components/media-library.tsx` | Left sidebar, video card list | Card, Badge, ScrollArea, Button |
| `src/components/video-canvas.tsx` | Center video viewport, variant chips | Badge |
| `src/components/control-panel.tsx` | Right sidebar, accordion container | Accordion, ScrollArea |
| `src/components/dubbing-method-accordion.tsx` | Checkbox group | Checkbox, Tooltip |
| `src/components/diarization-accordion.tsx` | Checkbox group | Checkbox, Tooltip |
| `src/components/voice-cloning-accordion.tsx` | Checkbox group | Checkbox, Tooltip |
| `src/hooks/use-studio-settings.ts` | Control panel state | — |

### Modify

| File | Change |
|---|---|
| `src/app/page.tsx` | Render `studio-layout` instead of `pipeline-page` |
| `src/app/layout.tsx` | Wrap with `TooltipProvider` |
| `src/hooks/use-pipeline.ts` | Accept settings, track variants |
| `src/lib/api.ts` | Add settings params to `synthesizeSpeech()` |
| `src/lib/types.ts` | Add `VideoVariant`, settings types |

### Keep (moved into right panel accordions or center canvas)

- `transcript-view.tsx` — rendered inside Transcript accordion
- `translation-view.tsx` — rendered inside Translation accordion
- `audio-player.tsx` — rendered inside Audio accordion
- `video-player.tsx` — embedded inside `video-canvas.tsx` as the playback element

### Remove after migration

- `pipeline-page.tsx` — replaced by `studio-layout.tsx`
- `pipeline-tracker.tsx` — pipeline status moves to badges on video cards
- `result-panel.tsx` — content distributes across right panel and center canvas
- `video-selector.tsx` — replaced by media library card selection

## shadcn Components

**Already installed:** Card, Badge, Button, ScrollArea, Tabs, Select, Progress, Separator, Skeleton, Alert

**Newly installed:** Accordion, Checkbox, Resizable, Tooltip

**shadcn MCP server** added for implementation: `claude mcp add --transport http shadcn https://www.shadcn.io/api/mcp`

## Visual Theme

Existing dark theme (globals.css) carries forward:
- Background: `hsl(240 10% 6%)` (zinc-950)
- Borders: `hsl(240 6% 18%)` (zinc-800)
- Primary accent: `hsl(45 93% 47%)` (golden yellow)
- Active selection: indigo-500 borders/backgrounds
- Fonts: DM Serif Display (headers), Geist (body), Geist Mono (code)
