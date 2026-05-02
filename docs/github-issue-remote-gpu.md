## Context

Students without a local NVIDIA GPU run Whisper (Speaches) and Chatterbox on a **lab GPU host** while Docker Compose (FastAPI + Next.js) runs on a **CPU-only** machine, using HTTP + SSH port forwards.

## Proposal

Document and ship helper assets:

- `docs/REMOTE_GPU_LAB.md`
- `scripts/ssh_inference_tunnel.sh`
- `scripts/remote-cluster/start-speaches.sh` and `start-chatterbox.sh`
- `contrib/lab-chatterbox-tts-api/` (reference copies of cluster-side Chatterbox patches + README)

## Acceptance criteria

- Main README links to `docs/REMOTE_GPU_LAB.md`.
- `.env.example` mentions `FW_WHISPER_BACKEND=remote`, `FW_WHISPER_API_URL`, and `CHATTERBOX_API_URL` for split-host setups.
