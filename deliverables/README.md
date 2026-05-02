# Course submission media (Notebook 7 — stitch + captions)

This folder holds **copies** of the final dubbed video and Spanish WebVTT captions for turn-in, matching the handout: **dubbed MP4** (audio remux) **plus sidecar WebVTT** (not burned into the video at stitch time).

## Files

| File | Description |
|------|-------------|
| `GYQ5yGV_-Oc_dubbed_baseline-c-fb1074a.mp4` | Dubbed output: original **video** stream (copied) + **Spanish TTS** audio. **Gitignored** (large). |
| `GYQ5yGV_-Oc_dubbed_baseline-c-fb1074a.es.vtt` | Rolling two-line **WebVTT** (same content the API serves at `GET /api/captions/{video_id}`). **Gitignored**. |
| `stitch_integration_executed.ipynb` | Notebook 7 run via `jupyter nbconvert --execute` (optional evidence). |
| `README.md` | This file — safe to **commit** so TAs see where artifacts live. |

**Video ID:** `GYQ5yGV_-Oc` (registry title: *Strait of Hormuz disruption threatens to shake global economy*).

**Playback:** Many players need the **`.vtt` loaded as an external subtitle** (the MP4 from P5 does not embed captions by default).

- **Dubbing Studio:** <http://localhost:8501> — run through **Stitch**, then open the dubbed variant; the UI loads captions from the API.
- **VLC:** Media → Open File → pick the `.mp4`; **Subtitle** → **Add Subtitle File** → pick the `.vtt`.

**QuickTime / AV1:** Source YouTube downloads are often **AV1**; QuickTime may report incompatible media. Prefer **VLC**, the Studio, or generate an optional **H.264 + hard-sub** preview (not canonical P5):

```bash
uv run python scripts/burn_in_dubbed_preview.py --help
```

## How these were produced (canonical P5)

1. Pipeline stages through **TTS**, then **`POST /api/stitch/{video_id}?config=c-fb1074a`** — ffmpeg **remux** (copy video, replace audio only).
2. **`GET /api/captions/GYQ5yGV_-Oc`** — materializes/refreshes `pipeline_data/api/dubbed_captions/<title>.vtt` if needed.
3. **Copy** the MP4 and VTT here with LMS-friendly names (no spaces).

## What to submit (per instructor)

- Push your **cloned repo** with **TA access** — **do not** `git add` the `.mp4` / `.vtt` here (they are **gitignored**; large binaries slow grading).
- **Zip** the **dubbed MP4** and the **matching `.vtt`** (or this whole folder) per course instructions, and note the **video ID** and **config** in your write-up.

Re-copy after any re-run of stitch or captions:

```bash
# From repo root, API on :8080
curl -sS -o /dev/null "http://localhost:8080/api/captions/GYQ5yGV_-Oc"
curl -sS -X POST "http://localhost:8080/api/stitch/GYQ5yGV_-Oc?config=c-fb1074a"
cp "pipeline_data/api/dubbed_videos/c-fb1074a/Strait of Hormuz disruption threatens to shake global economy.mp4" \
   "deliverables/GYQ5yGV_-Oc_dubbed_baseline-c-fb1074a.mp4"
cp "pipeline_data/api/dubbed_captions/Strait of Hormuz disruption threatens to shake global economy.vtt" \
   "deliverables/GYQ5yGV_-Oc_dubbed_baseline-c-fb1074a.es.vtt"
```
