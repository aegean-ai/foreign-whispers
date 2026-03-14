"""Application settings loaded from environment variables."""

from pathlib import Path

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

    # File paths
    base_dir: Path = Path(__file__).resolve().parent.parent
    ui_dir: Path = base_dir / "ui"

    model_config = {"env_prefix": "FW_"}


settings = Settings()
