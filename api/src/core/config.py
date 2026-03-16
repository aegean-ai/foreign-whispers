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

    # Backend selection: "local" or "remote"
    whisper_backend: str = "local"
    tts_backend: str = "local"

    # File paths
    base_dir: Path = Path(__file__).resolve().parent.parent.parent.parent
    ui_dir: Path = base_dir / "ui"

    # S3 storage
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""

    # PostgreSQL
    postgres_dsn: str = ""

    # vLLM / external inference
    vllm_base_url: str = ""

    # External service URLs
    xtts_api_url: str = "http://localhost:8020"
    whisper_api_url: str = "http://localhost:8000"

    model_config = {"env_prefix": "FW_"}


settings = Settings()
