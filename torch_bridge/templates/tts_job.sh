#!/bin/bash
#SBATCH --job-name=fw-tts
#SBATCH --account={{SLURM_ACCOUNT}}
{{SLURM_PARTITION_LINE}}#SBATCH --gres={{SLURM_GRES}}
#SBATCH --time={{SLURM_TIME}}
#SBATCH --output={{REMOTE_WORKDIR}}/slurm-%j.out
#SBATCH --error={{REMOTE_WORKDIR}}/slurm-%j.err

{{JOB_PROLOGUE}}

set -euo pipefail
cd "{{REMOTE_WORKDIR}}"

# Customize this block for Chatterbox / Coqui / another GPU TTS stack on Torch.
# Contract: read input.txt (UTF-8), write out.wav (PCM WAV).
python3 <<'PY'
from pathlib import Path

text = Path("input.txt").read_text(encoding="utf-8").strip()
if not text:
    raise SystemExit("empty input.txt")

raise SystemExit(
    "TTS job template is a stub: mount or edit torch_bridge/templates/tts_job.sh "
    "so it invokes your GPU TTS and writes out.wav (see docs in repo)."
)
PY
