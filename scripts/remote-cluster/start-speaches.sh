#!/usr/bin/env bash
# Start Speaches (Whisper) on a GPU host. Binds ${SPEACHES_BIND:-127.0.0.1}:${SPEACHES_PORT:-8000}.
#
# Prereq: Speaches install per Speaches docs (e.g. ~/speaches with uv).
#   SPEACHES_DIR=~/speaches ./scripts/remote-cluster/start-speaches.sh
#
# From laptop: ssh -N -L 8000:127.0.0.1:8000 user@gpu-host
# API .env: FW_WHISPER_BACKEND=remote, FW_WHISPER_API_URL=http://host.docker.internal:8000
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"

SPEACHES_PORT="${SPEACHES_PORT:-8000}"
SPEACHES_BIND="${SPEACHES_BIND:-127.0.0.1}"
if (exec 3<>/dev/tcp/127.0.0.1/"$SPEACHES_PORT") &>/dev/null 2>&1; then
  cat >&2 <<EOF
Error: 127.0.0.1:${SPEACHES_PORT} is already in use.

Use a free port:
  SPEACHES_PORT=8001 ./scripts/remote-cluster/start-speaches.sh
EOF
  exit 1
fi

SPEACHES_DIR="${SPEACHES_DIR:-$HOME/speaches}"
cd "$SPEACHES_DIR"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export WHISPER__MODEL="${WHISPER__MODEL:-Systran/faster-whisper-medium}"
echo "Speaches listening on http://${SPEACHES_BIND}:${SPEACHES_PORT}" >&2
exec uv run uvicorn --factory speaches.main:create_app --host "$SPEACHES_BIND" --port "$SPEACHES_PORT"
