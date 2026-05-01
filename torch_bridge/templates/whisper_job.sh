#!/bin/bash
#SBATCH --job-name=fw-whisper
#SBATCH --account={{SLURM_ACCOUNT}}
{{SLURM_PARTITION_LINE}}#SBATCH --gres={{SLURM_GRES}}
#SBATCH --time={{SLURM_TIME}}
#SBATCH --output={{REMOTE_WORKDIR}}/slurm-%j.out
#SBATCH --error={{REMOTE_WORKDIR}}/slurm-%j.err

{{JOB_PROLOGUE}}

set -euo pipefail
cd "{{REMOTE_WORKDIR}}"
export FW_WHISPER_MODEL="{{WHISPER_MODEL}}"

# Expect upload at path {{REMOTE_MEDIA}} (set by bridge); normalize to audio.wav
INPUT="{{REMOTE_MEDIA}}"
if [[ ! -f "$INPUT" ]]; then
  echo "missing input media: $INPUT" >&2
  exit 1
fi

if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -y -nostdin -i "$INPUT" -ar 16000 -ac 1 -c:a pcm_s16le audio.wav
else
  echo "ffmpeg not found — add it via FW_TORCH_JOB_PROLOGUE (e.g. module load ffmpeg)" >&2
  exit 1
fi

python3 <<'PY'
import json
import os

import whisper

work = os.getcwd()
os.chdir(work)
model_name = os.environ.get("FW_WHISPER_MODEL", "base")
model = whisper.load_model(model_name)
result = model.transcribe("audio.wav")
with open("transcript.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False)
PY
