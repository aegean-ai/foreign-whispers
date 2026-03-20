# Pipeline Config ID System

**Date**: 2026-03-19
**Status**: Approved
**Issue**: fw-4jc (studio frontend)

## Problem

The pipeline has three setting categories — dubbing (baseline, aligned), diarization (pyannote, whisper-based), and voice cloning (xtts, openvoice) — each with multiple options. When the user selects options across categories, the Cartesian product of active selections defines the set of pipeline runs. Each combination needs:

- A short, deterministic identifier for cache directories and filenames
- A human-readable label for the UI
- A mapping table visible in the sidebar

## Design Decisions

### Cartesian product with pruning

Only categories with at least one selection participate in the product. If dubbing = [baseline, aligned] and diarization = [pyannote] and voiceCloning = [], the product is 2 configs (not 4), because voiceCloning is excluded.

If nothing is selected in any category, default to `{dubbing: ["baseline"]}`.

Input arrays are deduplicated before computing the product.

### Hybrid ID: hash for files, label for display

- **Config ID**: `c-` prefix + first 7 hex chars of SHA-256 of a canonical JSON representation
- **Config Label**: Human-readable join of title-cased selected values with ` · ` separator

Example:
```
Selections: dubbing=aligned, diarization=pyannote, voiceCloning=[]
Canonical:  {"d":"aligned","i":"pyannote"}
Hash:       SHA-256('{"d":"aligned","i":"pyannote"}') → first 7 hex
ID:         c-3a8f1b2
Label:      Aligned · Pyannote
```

### Frontend-only registry

The frontend computes config IDs from user selections and passes them to the API as query params. The API uses the ID as a directory name but does not maintain its own registry or resolve IDs back to settings.

## Canonical JSON Format

Keys are shortened to single letters, sorted alphabetically:
- `d` → dubbing
- `i` → diarization (mnemonic: "identification")
- `v` → voiceCloning

Each config entry in the Cartesian product contains exactly **one** value per participating category. The canonical form uses plain strings (not arrays) since each entry has one value per key. Empty categories are omitted entirely.

```
{ dubbing: ["baseline", "aligned"], diarization: ["pyannote"] }

→ Entry 1: {"d":"baseline","i":"pyannote"}  → c-XXXXXXX "Baseline · Pyannote"
→ Entry 2: {"d":"aligned","i":"pyannote"}   → c-YYYYYYY "Aligned · Pyannote"
```

## Hashing

Use a **synchronous** hash function — djb2 — not `crypto.subtle` (which is async and would complicate the synchronous reducer). djb2 is sufficient for this use case (small config space, no security requirement).

```typescript
function djb2(str: string): string {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) >>> 0;
  }
  return hash.toString(16).padStart(7, "0").slice(0, 7);
}
```

Config ID = `"c-" + djb2(canonicalJson)`.

## Types

```typescript
// lib/config-id.ts

interface ConfigEntry {
  id: string;            // "c-3a8f1b2"
  label: string;         // "Aligned · Pyannote"
  dubbing?: string;      // single value from dubbing selections
  diarization?: string;  // single value from diarization selections
  voiceCloning?: string; // single value from voiceCloning selections
}
```

## API Contract

All pipeline endpoints that produce config-specific artifacts accept `?config=<id>` and `?alignment=true|false`:

```
POST /api/tts/{video_id}?config=c-3a8f1b2&alignment=true
POST /api/stitch/{video_id}?config=c-3a8f1b2
GET  /api/video/{video_id}?config=c-3a8f1b2
GET  /api/audio/{video_id}?config=c-3a8f1b2
```

The `config` param is used as a subdirectory name. The `alignment` param is an explicit boolean sent alongside config — the API does not derive alignment from the config ID (it's opaque to the API).

**Validation**: The `config` param must match `^c-[0-9a-f]{7}$` to prevent path traversal.

### Migration from `?mode=`

The current `?mode=baseline|aligned` parameter is replaced by `?config=` + `?alignment=`. Backwards compatibility: the API falls back to legacy flat directories if the config subdirectory doesn't exist. This fallback applies to both video and audio GET endpoints.

## File Layout

```
pipeline_data/
  translated_audio/
    c-3a8f1b2/                    # baseline + pyannote
      Alysa Liu....wav
      Alysa Liu....align.json
    c-9e2d4a1/                    # aligned + pyannote
      Alysa Liu....wav
      Alysa Liu....align.json
  translated_video/
    c-3a8f1b2/
      Alysa Liu....mp4
    c-9e2d4a1/
      Alysa Liu....mp4
```

## Frontend Changes

### New: `lib/config-id.ts`

Exports:
- `computeConfigEntries(settings: StudioSettings): ConfigEntry[]` — Cartesian product of active selections (deduplicated), each with a deterministic hash ID and title-cased label
- `computeConfigId(entry: Pick<ConfigEntry, 'dubbing' | 'diarization' | 'voiceCloning'>): string` — hash a single combination
- `computeConfigLabel(entry: Pick<ConfigEntry, 'dubbing' | 'diarization' | 'voiceCloning'>): string` — human label

All functions are synchronous (djb2 hash).

### Modified: `hooks/use-pipeline.ts`

- Import `computeConfigEntries`
- Compute entries eagerly in `runPipeline` (before dispatch) since `computeConfigEntries` is sync
- On START, pass computed `ConfigEntry[]` in the action payload; the reducer creates one `VideoVariant` per entry (with `configId` field)
- Replace the dubbing-mode loop with a config-entry loop:
  ```typescript
  const configs = computeConfigEntries(settings);
  for (const cfg of configs) {
    dispatch({ type: "SELECT_VARIANT", variantId: makeVariantId(video.id, cfg.id) });
    const alignment = cfg.dubbing === "aligned";
    await run("tts", () => synthesizeSpeech(dl.video_id, cfg.id, alignment));
    await run("stitch", () => stitchVideo(dl.video_id, cfg.id));
  }
  ```
- `SELECT_VARIANT` dispatched before each config's TTS+stitch so `activeVariantId` tracks the correct variant for error handling
- Variant ID format: `makeVariantId(videoId, configId)` → `${videoId}::${configId}` (uses `::` delimiter, not `_`, to avoid ambiguity with YouTube IDs that contain hyphens/underscores)

### Modified: `lib/api.ts`

Replace `mode: "baseline" | "aligned"` parameter with `config: string` on:
- `synthesizeSpeech(videoId, config, alignment)` — sends `?config=...&alignment=true|false`
- `stitchVideo(videoId, config)` — sends `?config=...`
- `getVideoUrl(videoId, config)` — sends `?config=...`
- `getAudioUrl(videoId, config)` — sends `?config=...`

### Modified: `lib/types.ts`

`VideoVariant` gains a `configId` field:
```typescript
interface VideoVariant {
  id: string;              // "videoId::c-3a8f1b2"
  sourceVideoId: string;
  configId: string;        // "c-3a8f1b2"
  label: string;           // "Aligned · Pyannote"
  settings: StudioSettings;
  status: "complete" | "processing" | "error";
}
```

### Modified: `components/video-canvas.tsx`

Read `configId` directly from the active `VideoVariant` object (not by parsing the variant ID string) and pass to `getVideoUrl(videoId, variant.configId)`.

### Modified: `components/app-sidebar.tsx`

Add a **Configurations** summary below the accordion:

```
Pipeline Settings
  ▸ Dubbing Methods     [✓ baseline, ✓ aligned]
  ▸ Diarization         [✓ pyannote]
  ▸ Voice Cloning       []

  Configurations (2)
  ┌─────────┬───────────────────────┐
  │ c-3a8f1 │ Baseline · Pyannote   │
  │ c-9e2d4 │ Aligned · Pyannote    │
  └─────────┴───────────────────────┘
```

Display as a compact list with truncated hash and label. Updates reactively as settings change.

## API Changes

### Modified: `api/src/routers/tts.py`

- Replace `mode` query param with:
  - `config: str = Query("default", pattern=r"^c-[0-9a-f]{7}$")`
  - `alignment: bool = Query(False)`
- Use `config` for subdirectory: `translated_audio/{config}/`
- Pass `alignment` boolean directly to `tts_service.text_file_to_speech(..., alignment=alignment)`
- Response body: `{"video_id": ..., "audio_path": ..., "config": ...}`

### Modified: `api/src/routers/stitch.py`

- Replace `mode` query param with `config: str = Query("default", pattern=r"^c-[0-9a-f]{7}$")`
- Use `config` for subdirectory: `translated_video/{config}/`
- Fallback to legacy flat dir for backwards compat on both POST and GET endpoints
- Response body: `{"video_id": ..., "video_path": ..., "config": ...}`

### Modified: `api/src/routers/stitch.py` (video/audio serving)

- Replace `mode` query param with `config: str` on GET endpoints (`/api/video/`, `/api/audio/`)
- Both endpoints fall back to legacy flat dir if config subdir doesn't exist

## Stage Tracking for Multi-Config Runs

The current `stages` record has one slot per stage name (download, transcribe, translate, tts, stitch). When running multiple configs, the TTS and stitch stages execute multiple times.

**Approach**: The stages record tracks the *current iteration* only. Each config's TTS+stitch overwrites the previous status. The pipeline table shows the latest stage state. The variant badges (in the video canvas) show per-variant completion status. This is acceptable because:

- Download, transcribe, and translate run once (shared across configs)
- TTS and stitch run sequentially per config — only one is active at a time
- The status bar shows which config is currently processing
- The variant selector shows which outputs are complete

The `activeVariantId` is updated via `SELECT_VARIANT` before each config's TTS+stitch loop, so `STAGE_ERROR` marks the correct variant.

## Edge Cases

1. **No selections**: Default to single config entry `{dubbing: "baseline"}`
2. **Hash collision**: djb2 at 7 hex chars — collision probability negligible for < 100 configs
3. **Duplicate settings values**: Deduplicated before computing the Cartesian product
4. **Path traversal**: `config` param validated with `^c-[0-9a-f]{7}$` regex on API
5. **Variant ID parsing**: Use `::` delimiter and read `configId` from variant object, not by string splitting
6. **Label casing**: All labels are title-cased (first letter uppercase, rest lowercase)
