#!/usr/bin/env bash
# Start Chatterbox TTS API on a GPU host (lab cluster). Listens on
# ${CHATTERBOX_BIND:-127.0.0.1}:${CHATTERBOX_PORT:-8020}.
#
# Prereq: clone https://github.com/travisvn/chatterbox-tts-api (or your fork),
# apply patches under contrib/lab-chatterbox-tts-api/ if needed, then:
#   CHATTERBOX_DIR=~/chatterbox-tts-api ./scripts/remote-cluster/start-chatterbox.sh
#
# Laptop + Docker: SSH tunnel from the machine running compose, e.g.
#   ssh -N -L 8020:127.0.0.1:8020 user@gpu-host
# Point CHATTERBOX_API_URL at host.docker.internal:8020 (see .env.example).
#
# Pick GPU via CUDA_VISIBLE_DEVICES (index or MIG UUID on shared nodes).
set -euo pipefail
export PATH="${HOME}/.local/bin:${PATH}"

CHATTERBOX_PORT="${CHATTERBOX_PORT:-8020}"
CHATTERBOX_BIND="${CHATTERBOX_BIND:-127.0.0.1}"
if (exec 3<>/dev/tcp/127.0.0.1/"$CHATTERBOX_PORT") &>/dev/null 2>&1; then
  cat >&2 <<EOF
Error: 127.0.0.1:${CHATTERBOX_PORT} is already in use.

Use a free port:
  CHATTERBOX_PORT=8021 ./scripts/remote-cluster/start-chatterbox.sh
EOF
  exit 1
fi

CHATTERBOX_DIR="${CHATTERBOX_DIR:-$HOME/chatterbox-tts-api}"
cd "$CHATTERBOX_DIR"
# Default to first visible GPU; override for MIG / policy, e.g. CUDA_VISIBLE_DEVICES=GPU-xxxx
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export HOST="$CHATTERBOX_BIND"
export PORT="$CHATTERBOX_PORT"
export DEVICE="${DEVICE:-cuda}"
export DEFAULT_MODEL="${DEFAULT_MODEL:-multilingual}"
echo "Chatterbox listening on http://${CHATTERBOX_BIND}:${CHATTERBOX_PORT}" >&2
exec uv run python main.py
