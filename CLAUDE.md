# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a multi-project repository containing student submissions for the **Foreign Whispers** course project. Each team built a pipeline that accepts YouTube videos from the [60 Minutes Interviews playlist](https://www.youtube.com/playlist?list=PLI1yx5Z0Lrv77D_g1tvF9u3FVqnrNbCRL) and outputs the video with spoken and written subtitles in another language.

The project spec defined six milestones:
1. Download videos + closed captions from YouTube (ground truth English)
2. Speech-to-text via Whisper
3. English → target language translation (no commercial APIs: no Google/Microsoft/OpenAI Translate)
4. Translated text → speech via open-source TTS
5a. Streamlit UI on Hugging Face Spaces + 30-second pitch video
6. (Extra credit) Django app deployed via Docker Compose

```
foreign-whispers/
├── app.py                       # Streamlit UI entry point
├── main.py                      # Re-exports FastAPI app from api/src/
├── api/src/                     # Layered FastAPI backend
│   ├── main.py                  # App factory (create_app)
│   ├── core/config.py           # Pydantic settings
│   ├── core/dependencies.py     # FastAPI Depends providers
│   ├── routers/                 # Route modules
│   ├── schemas/                 # Pydantic request/response models
│   ├── services/                # Business logic
│   └── inference/               # Whisper/TTS backend abstraction
├── download_video.py
├── transcribe.py
├── translate_en_to_es.py
├── tts_es.py
├── translated_output.py
├── transcriptions_en/           # 10 processed transcripts
└── transcriptions_es/           # 10 translated transcripts
```

**The main gaps to address** (tracked as beads issues) are TTS audio-video synchronisation (`tts_es.py` has no timestamp alignment — issue `ccu`) and missing Hugging Face Spaces deployment (issue `jhg`).

## Common AI Pipeline

All three projects implement variations of the same pipeline:

```
YouTube URL → Download video + captions → Transcribe (Whisper) → Translate → TTS → Embed audio/subs → Output video
```

**Technologies shared across projects:**
- `openai-whisper` — speech-to-text transcription
- `pytube` / `yt-dlp` — video downloading
- `youtube-transcript-api` — caption extraction
- `moviepy` — video composition
- Mozilla `TTS` — text-to-speech synthesis

## Streamlit App (root)

### Running

```bash
uv sync
streamlit run app.py
```

FastAPI backend:
```bash
uvicorn main:app --reload
```

### Architecture

Flat utility-module structure — each processing step is its own file:
- `download_video.py`
- `transcribe.py`
- `translate_en_to_es.py` — uses `argostranslate` (OpenNMT, offline)
- `tts_es.py`
- `translated_output.py` — video stitching

`app.py` coordinates these modules; it caches results by video ID to skip reprocessing.

Intermediate files are stored under `./ui/` subdirectories: `raw_video/`, `raw_transcription/`, `translated_transcription/`, `translated_audio/`, `translated_video/`.

Transcripts are stored as JSON with segment structure: `[{"start": float, "end": float, "text": str}, ...]`

## Development Notes

- ffmpeg must be installed system-wide for moviepy/audio processing to work
- Whisper model is downloaded on first use and cached by the library; GPU acceleration requires CUDA
- `argostranslate` language packs must be downloaded before first use (handled inside `translate_en_to_es.py` via `download_and_install_package()`)
- `translated_output.py` requires ImageMagick system-wide for `TextClip` subtitle rendering (see beads issue `ttl`)
