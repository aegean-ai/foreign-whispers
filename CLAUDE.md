# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

**Foreign Whispers** — a pipeline that accepts YouTube videos and outputs the video with spoken and written subtitles in a target language. The pipeline covers:

1. Download video + closed captions from YouTube
2. Speech-to-text via Whisper
3. Source → target language translation (offline, via `argostranslate`)
4. Translated text → speech via open-source TTS (Chatterbox)
5. Next.js frontend + FastAPI backend

```text
foreign-whispers/
├── api/src/                     # Layered FastAPI backend
│   ├── main.py                  # App factory (create_app)
│   ├── core/config.py           # Pydantic settings (env-driven)
│   ├── core/dependencies.py     # FastAPI Depends providers
│   ├── routers/                 # Route modules (videos, pipeline, align)
│   ├── schemas/                 # Pydantic request/response models
│   ├── services/                # Business logic
│   └── inference/               # Whisper/TTS backend abstraction
├── foreign_whispers/            # Alignment/evaluation library
│   ├── alignment.py             # global_align(), AlignAction, SegmentMetrics
│   ├── backends.py              # DurationAwareTTSBackend ABC
│   ├── vad.py                   # Silero VAD wrapper
│   ├── diarization.py           # pyannote.audio wrapper
│   ├── reranking.py             # Failure analysis + translation re-ranking stub
│   └── evaluation.py           # clip_evaluation_report()
├── frontend/                    # Next.js UI (port 8501 in Docker)
├── video_registry.yml           # Single source of truth for pipeline videos
├── pipeline_data/api/            # Runtime artifacts — model-namespaced dirs
│   ├── videos/                  # Source MP4s
│   ├── youtube_captions/        # yt-dlp caption JSON
│   ├── transcriptions/whisper/  # Whisper output
│   ├── translations/argos/      # argostranslate output
│   ├── tts_audio/chatterbox/     # TTS WAV per config
│   ├── dubbed_captions/         # Target-language VTT
│   └── dubbed_videos/           # Final dubbed MP4 per config
└── docker-compose.yml           # All services
```

## Running the App

**Always use Docker Compose — never launch with `uvicorn` or `next dev` directly.**

This host has an NVIDIA GPU; always use the `nvidia` profile:

```bash
docker compose --profile nvidia up -d
```

- Frontend (Next.js): <http://localhost:8501>
- API (FastAPI): <http://localhost:8080>
- STT (Whisper/speaches): <http://localhost:8000>
- TTS (Chatterbox): <http://localhost:8020>

After changing Python source or `video_registry.yml`, rebuild the API image:

```bash
docker compose --profile nvidia build api
docker compose --profile nvidia up -d api
```

To stop all services:

```bash
docker compose --profile nvidia down
```

To tail logs:

```bash
docker compose --profile nvidia logs -f
```

## Video Registry

`video_registry.yml` is the single source of truth for all videos in the pipeline. Add entries there; the API reads it at startup to populate `/api/videos`. After adding a video, rebuild and restart the API container (see above).

## Architecture

### Pipeline flow

```text
YouTube URL → yt-dlp download → Whisper STT → argostranslate → Chatterbox TTS → moviepy/ffmpeg stitch → output video
```

### Key design decisions

- `video_registry.yml` drives the video list; no database.
- `foreign_whispers` library handles temporal alignment between source-language segments and target-language TTS audio.
- Pipeline directory names are centralised in `api/src/core/config.py` as `@property` methods on `Settings`. Use `settings.videos_dir`, `settings.transcriptions_dir`, etc. — never hardcode directory names in routers.
- Optional heavy deps (`silero-vad`, `pyannote.audio`, `logfire`) degrade gracefully when absent.

## Open Issues

- `fw-tov`: TTS temporal alignment implementation (design doc: `docs/superpowers/specs/2026-03-17-tts-temporal-alignment-design.md`)
- `jhg`: Hugging Face Spaces deployment
