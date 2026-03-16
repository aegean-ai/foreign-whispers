# AI Project Fall 2023
Members:
  - Rafik Saad
  - Banani Ghosh

## Architecture

```mermaid
flowchart LR
    subgraph Input
        YT[YouTube URL]
    end

    subgraph Pipeline
        DL[Download\nyt-dlp / pytube]
        TR[Transcribe\nWhisper]
        TL[Translate\nargostranslate\nOpenNMT]
        TTS[Text-to-Speech\nCoqui TTS / XTTS-v2]
        ST[Stitch Video\nmoviepy + ImageMagick]
    end

    subgraph Output
        VID[Translated Video\nw/ dubbed audio & subtitles]
    end

    subgraph Frontends
        SL[Streamlit UI\napp.py]
        FA[FastAPI Backend\nmain.py]
    end

    YT --> DL --> TR --> TL --> TTS --> ST --> VID

    SL -- orchestrates --> DL
    FA -- "/download\n/transcribe\n/translate\n/tts\n/stitch" --> DL

    classDef default fill:#37474f,color:#fff,stroke:#546e7a
    classDef pipeline fill:#0277bd,color:#fff,stroke:#01579b
    classDef frontend fill:#00695c,color:#fff,stroke:#004d40
    classDef io fill:#4527a0,color:#fff,stroke:#311b92

    class YT,VID io
    class DL,TR,TL,TTS,ST pipeline
    class SL,FA frontend
```

## Running

```bash
uv sync
streamlit run app.py
```

FastAPI backend:
```bash
uvicorn api.src.main:app --reload
```

Docker Compose (includes Whisper + XTTS GPU services):
```bash
docker compose up
```

## Hugging Face Space

[pantelism/foreign-whispers](https://huggingface.co/spaces/pantelism/foreign-whispers) — live Streamlit app on HF Spaces.

## Pitch Video

[Pete Hegseth: The 60 Minutes Interview](https://www.youtube.com/watch?v=7hPDiwJOHl4) — sample 60 Minutes episode used to demonstrate the Foreign Whispers dubbing pipeline.

## Milestones

1. Download videos + captions from YouTube (pytube / yt-dlp)
2. Transcribe with Whisper
3. Translate with argostranslate (OpenNMT, offline)
4. Text-to-speech with Coqui TTS / XTTS-v2
5. Streamlit UI + pitch video
6. FastAPI backend (`api/src/`) with endpoints for each pipeline stage
