"""Foreign Whispers FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ML models once at startup, release on shutdown."""
    logger.info("Loading Whisper model (%s)...", settings.whisper_model)
    import whisper

    app.state.whisper_model = whisper.load_model(settings.whisper_model)
    logger.info("Whisper model loaded.")

    logger.info("Loading TTS model (%s)...", settings.tts_model_name)
    from TTS.api import TTS

    app.state.tts_model = TTS(model_name=settings.tts_model_name, progress_bar=False)
    logger.info("TTS model loaded.")

    yield

    # Cleanup
    del app.state.whisper_model
    del app.state.tts_model
    logger.info("Models unloaded.")


app = FastAPI(
    title=settings.app_title,
    lifespan=lifespan,
)

if settings.cors_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/healthz")
async def healthz():
    """Health check endpoint."""
    return {"status": "ok"}
