#!/usr/bin/env bash
# Open SSH local port forwards so Docker on this Mac can reach GPU inference on a
# remote host. Run this on your laptop and leave it running while you use the stack.
#
# On the REMOTE machine, STT and TTS servers must listen on 127.0.0.1:8000 and
# 127.0.0.1:8020 (see Cursor prompt for the remote agent).
#
# Root .env (api loads via docker compose env_file) — use free local ports if
# 8000/8020 are taken (e.g. by Cursor), then match the -L below:
#   FW_WHISPER_BACKEND=remote
#   FW_WHISPER_API_URL=http://host.docker.internal:18000
#   CHATTERBOX_API_URL=http://host.docker.internal:18020
#   FW_CHATTERBOX_SKIP_HEAVY_PROBE=1
#
# Default compose uses bridge networking (not host) on Mac so published
# localhost:8080 / :8501 work; host.docker.internal reaches the Mac SSH listener.
#
set -euo pipefail

REMOTE="${1:?usage: $0 user@lambda-minerva}"

exec ssh -N \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -L 8000:127.0.0.1:8000 \
  -L 8020:127.0.0.1:8020 \
  "$REMOTE"
