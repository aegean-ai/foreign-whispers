"""Environment-driven settings for the Torch job bridge."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FW_TORCH_", extra="ignore")

    ssh_host: str = Field(default="login.torch.hpc.nyu.edu", description="Torch login hostname")
    ssh_user: str = Field(default="", description="SSH user (NetID); required")
    ssh_identity_file: str = Field(
        default="",
        description="Path to private key inside the container (e.g. /ssh/id_ed25519)",
    )
    ssh_extra_args: str = Field(
        default="-o StrictHostKeyChecking=no -o ServerAliveInterval=60",
        description="Extra args passed to ssh/scp (space-separated)",
    )

    remote_work_root: str = Field(
        default="",
        description="Absolute path on Torch for per-job dirs (e.g. $SCRATCH/fw-bridge). Required.",
    )

    slurm_account: str = Field(default="", description="sbatch --account=… (required on Torch)")
    slurm_partition: str = Field(default="", description="Optional #SBATCH --partition")
    slurm_gres: str = Field(default="gpu:1", description="#SBATCH --gres value, e.g. gpu:1")
    slurm_time: str = Field(default="01:00:00", description="#SBATCH --time limit")

    whisper_model: str = Field(default="base", description="Whisper model name passed into the cluster job")
    job_poll_interval_s: float = Field(default=3.0)
    job_timeout_s: float = Field(default=3600.0)

    whisper_template: Path = Field(
        default=Path(__file__).resolve().parent / "templates" / "whisper_job.sh",
    )
    tts_template: Path = Field(
        default=Path(__file__).resolve().parent / "templates" / "tts_job.sh",
    )

    job_prologue: str = Field(
        default="",
        description="Bash lines inserted after SBATCH headers (module load, conda activate, …)",
    )


settings = Settings()
