"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_title: str = "Foreign Whispers API"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # CORS
    cors_enabled: bool = True
    cors_origins: list[str] = ["*"]

    # Model configuration
    whisper_model: str = "base"
    tts_model_name: str = "tts_models/es/css10/vits"

    # Backend selection: "local" or "remote"
    whisper_backend: str = "local"
    tts_backend: str = "local"

    # Model directory names — change these when swapping backends
    stt_model_dir: str = "whisper"
    translation_model_dir: str = "argos"
    tts_model_dir: str = "xtts-v2"

    # File paths
    base_dir: Path = Path(__file__).resolve().parent.parent.parent.parent
    data_dir: Path = base_dir / "pipeline_data" / "api"
    # Legacy alias — kept for backwards compatibility with volume mounts
    ui_dir: Path = data_dir

    # ── pipeline directory layout ───────────────────────────────────────
    # Centralised here so a rename is a one-line change.

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def youtube_captions_dir(self) -> Path:
        return self.data_dir / "youtube_captions"

    @property
    def transcriptions_dir(self) -> Path:
        return self.data_dir / "transcriptions" / self.stt_model_dir

    @property
    def translations_dir(self) -> Path:
        return self.data_dir / "translations" / self.translation_model_dir

    @property
    def tts_audio_dir(self) -> Path:
        return self.data_dir / "tts_audio" / self.tts_model_dir

    @property
    def dubbed_videos_dir(self) -> Path:
        return self.data_dir / "dubbed_videos"

    @property
    def dubbed_captions_dir(self) -> Path:
        return self.data_dir / "dubbed_captions"

    # S3 storage
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # PostgreSQL
    database_url: str = ""
    database_echo: bool = False

    # Backwards-compatible alias so FW_POSTGRES_DSN still works.
    postgres_dsn: str = ""

    # vLLM / external inference
    vllm_base_url: str = ""

    # External service URLs
    xtts_api_url: str = "http://localhost:8020"
    whisper_api_url: str = "http://localhost:8000"

    # HuggingFace token for pyannote speaker diarization model
    hf_token: str = ""

    # Logfire write token — set via FW_LOGFIRE_WRITE_TOKEN (or put in .env)
    logfire_write_token: str = ""

    model_config = {"env_prefix": "FW_"}

    @model_validator(mode="after")
    def _sync_postgres_dsn_alias(self) -> "Settings":
        """If database_url is empty but postgres_dsn was set, copy it over."""
        if not self.database_url and self.postgres_dsn:
            self.database_url = self.postgres_dsn
        return self


settings = Settings()
