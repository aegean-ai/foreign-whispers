"""SSH + Slurm orchestration for one-off GPU jobs on Torch."""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from torch_bridge.config import settings

logger = logging.getLogger(__name__)


def _ssh_base() -> list[str]:
    if not settings.ssh_user:
        raise RuntimeError("FW_TORCH_SSH_USER is not set")
    cmd = ["ssh", "-o", "BatchMode=yes"]
    for arg in settings.ssh_extra_args.split():
        if arg.strip():
            cmd.append(arg.strip())
    if settings.ssh_identity_file:
        cmd.extend(["-i", settings.ssh_identity_file])
    cmd.append(f"{settings.ssh_user}@{settings.ssh_host}")
    return cmd


def _scp_base() -> list[str]:
    cmd = ["scp", "-o", "BatchMode=yes"]
    for arg in settings.ssh_extra_args.split():
        if arg.strip():
            cmd.append(arg.strip())
    if settings.ssh_identity_file:
        cmd.extend(["-i", settings.ssh_identity_file])
    return cmd


def run_remote_shell(script: str) -> str:
    """Run a bash script on the login node (non-interactive)."""
    base = _ssh_base()
    proc = subprocess.run(
        [*base, script],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        logger.error("remote shell failed: %s", proc.stderr)
        raise RuntimeError(f"SSH command failed (exit {proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def scp_to_remote(local_path: Path, remote_path: str) -> None:
    dest = f"{settings.ssh_user}@{settings.ssh_host}:{remote_path}"
    proc = subprocess.run(
        [*_scp_base(), str(local_path), dest],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"scp upload failed: {proc.stderr.strip()}")


def scp_from_remote(remote_path: str, local_path: Path) -> None:
    src = f"{settings.ssh_user}@{settings.ssh_host}:{remote_path}"
    proc = subprocess.run(
        [*_scp_base(), src, str(local_path)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"scp download failed: {proc.stderr.strip()}")


def _render_template(template_path: Path, replacements: dict[str, str]) -> str:
    text = template_path.read_text()
    for key, val in replacements.items():
        text = text.replace(f"{{{{{key}}}}}", val)
    return text


def _partition_line() -> str:
    if settings.slurm_partition:
        return f"#SBATCH --partition={settings.slurm_partition}\n"
    return "\n"


def _sbatch_and_wait(remote_workdir: str, job_script_name: str, success_remote_path: str) -> None:
    inner = (
        f"cd {shlex.quote(remote_workdir)} && "
        f"JOB_OUT=$(sbatch --parsable {shlex.quote(job_script_name)}) && echo \"$JOB_OUT\""
    )
    out = run_remote_shell(inner).strip()
    job_id = out.splitlines()[-1].strip().split(";")[0].strip()
    if not job_id.isdigit():
        raise RuntimeError(f"Unexpected sbatch output: {out!r}")

    deadline = time.monotonic() + settings.job_timeout_s
    while time.monotonic() < deadline:
        if run_remote_shell(f"test -f {shlex.quote(success_remote_path)} && echo 1").strip() == "1":
            return

        in_queue = run_remote_shell(f"squeue -j {job_id} -h 2>/dev/null | wc -l").strip()
        if in_queue == "0":
            time.sleep(2)
            if run_remote_shell(f"test -f {shlex.quote(success_remote_path)} && echo 1").strip() == "1":
                return
            st = run_remote_shell(
                f"sacct -j {job_id} -X -n -o State,ExitCode -P 2>/dev/null | head -1"
            ).strip()
            log_tail = run_remote_shell(
                f"tail -n 120 {shlex.quote(remote_workdir)}/slurm-{job_id}.err 2>/dev/null || "
                f"tail -n 120 {shlex.quote(remote_workdir)}/slurm-{job_id}.out 2>/dev/null || true"
            )
            raise RuntimeError(
                f"Slurm job {job_id} finished without success file {success_remote_path!r}. "
                f"sacct: {st!r}\n--- logs ---\n{log_tail}"
            )

        time.sleep(settings.job_poll_interval_s)

    raise TimeoutError(f"Slurm job {job_id} did not produce output within {settings.job_timeout_s}s")


def run_whisper_job(local_media: Path) -> dict:
    """Upload media, run whisper Slurm job, download transcript JSON (whisper-style dict)."""
    if not settings.remote_work_root:
        raise RuntimeError("FW_TORCH_REMOTE_WORK_ROOT must be set to an absolute path on Torch")

    job_token = uuid.uuid4().hex[:16]
    remote_dir = f"{settings.remote_work_root.rstrip('/')}/fw-{job_token}"
    run_remote_shell(f"mkdir -p {shlex.quote(remote_dir)}")

    remote_media = f"{remote_dir}/input{local_media.suffix}"
    scp_to_remote(local_media, remote_media)

    repl = {
        "SLURM_ACCOUNT": settings.slurm_account,
        "SLURM_PARTITION_LINE": _partition_line(),
        "SLURM_GRES": settings.slurm_gres,
        "SLURM_TIME": settings.slurm_time,
        "REMOTE_WORKDIR": remote_dir,
        "REMOTE_MEDIA": remote_media,
        "WHISPER_MODEL": settings.whisper_model,
        "JOB_PROLOGUE": settings.job_prologue,
    }
    script = _render_template(settings.whisper_template, repl)
    local_script = Path(f"/tmp/fw-torch-whisper-{job_token}.sh")
    local_script.write_text(script)
    scp_to_remote(local_script, f"{remote_dir}/job.sh")
    local_script.unlink(missing_ok=True)

    success = f"{remote_dir}/transcript.json"
    _sbatch_and_wait(remote_dir, "job.sh", success)

    out_json = Path(f"/tmp/fw-torch-out-{job_token}.json")
    try:
        scp_from_remote(success, out_json)
        return json.loads(out_json.read_text(encoding="utf-8"))
    finally:
        out_json.unlink(missing_ok=True)


def run_tts_job(text: str, local_voice_wav: Path | None) -> bytes:
    """Upload text (and optional reference voice), run TTS Slurm job, download WAV bytes."""
    if not settings.remote_work_root:
        raise RuntimeError("FW_TORCH_REMOTE_WORK_ROOT must be set to an absolute path on Torch")

    job_token = uuid.uuid4().hex[:16]
    remote_dir = f"{settings.remote_work_root.rstrip('/')}/fw-tts-{job_token}"
    run_remote_shell(f"mkdir -p {shlex.quote(remote_dir)}")

    local_text = Path(f"/tmp/fw-torch-tts-{job_token}.txt")
    local_text.write_text(text, encoding="utf-8")
    scp_to_remote(local_text, f"{remote_dir}/input.txt")
    local_text.unlink(missing_ok=True)

    if local_voice_wav is not None and local_voice_wav.is_file():
        scp_to_remote(local_voice_wav, f"{remote_dir}/voice_ref.wav")

    repl = {
        "SLURM_ACCOUNT": settings.slurm_account,
        "SLURM_PARTITION_LINE": _partition_line(),
        "SLURM_GRES": settings.slurm_gres,
        "SLURM_TIME": settings.slurm_time,
        "REMOTE_WORKDIR": remote_dir,
        "JOB_PROLOGUE": settings.job_prologue,
        "HAS_VOICE": "1" if local_voice_wav and local_voice_wav.is_file() else "0",
    }
    script = _render_template(settings.tts_template, repl)
    local_script = Path(f"/tmp/fw-torch-tts-{job_token}.sh")
    local_script.write_text(script)
    scp_to_remote(local_script, f"{remote_dir}/job.sh")
    local_script.unlink(missing_ok=True)

    success = f"{remote_dir}/out.wav"
    _sbatch_and_wait(remote_dir, "job.sh", success)

    out_wav = Path(f"/tmp/fw-torch-tts-out-{job_token}.wav")
    try:
        scp_from_remote(success, out_wav)
        return out_wav.read_bytes()
    finally:
        out_wav.unlink(missing_ok=True)


def check_ssh() -> tuple[bool, str]:
    """Return (ok, message) for /health."""
    try:
        if not settings.ssh_user:
            return False, "FW_TORCH_SSH_USER is not set"
        if not settings.remote_work_root:
            return False, "FW_TORCH_REMOTE_WORK_ROOT is not set"
        if not settings.slurm_account:
            return False, "FW_TORCH_SLURM_ACCOUNT is not set"
        out = run_remote_shell("echo FW_TORCH_BRIDGE_OK")
        if "FW_TORCH_BRIDGE_OK" not in out:
            return False, f"unexpected ssh output: {out!r}"
        return True, "ssh_ok"
    except Exception as exc:
        return False, str(exc)
