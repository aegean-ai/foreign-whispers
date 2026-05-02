# Remote GPU inference (lab cluster)

The course stack assumes **Whisper** (~:8000) and **Chatterbox** (~:8020) on a machine with an NVIDIA GPU. If your laptop or CI host is **CPU-only**, run STT/TTS on a **lab GPU node** and point the Foreign Whispers API at those HTTP endpoints.

## Layout

| Role | Typical host | Ports |
|------|----------------|-------|
| Speaches (Whisper) | GPU server | `8000` |
| Chatterbox TTS API | GPU server | `8020` |
| Docker Compose (API + frontend) | Your laptop / CPU VM | `8080`, `8501` |

## GPU server

1. Install [Speaches](https://github.com/speaches-ai/speaches) and [chatterbox-tts-api](https://github.com/travisvn/chatterbox-tts-api) (or your fork). Apply any patches from `contrib/lab-chatterbox-tts-api/` if required by your CUDA/PyTorch version.
2. From this repository’s clone on the server (or copy the scripts):

   ```bash
   chmod +x scripts/remote-cluster/*.sh
   SPEACHES_DIR=~/speaches ./scripts/remote-cluster/start-speaches.sh
   CHATTERBOX_DIR=~/chatterbox-tts-api ./scripts/remote-cluster/start-chatterbox.sh
   ```

3. Set `CUDA_VISIBLE_DEVICES` to the GPU or MIG slice you are allowed to use on shared clusters.

## CPU client (Docker)

1. Open SSH local forwards so containers can reach the GPU host through your Mac:

   ```bash
   ./scripts/ssh_inference_tunnel.sh user@your-lab-gpu-host
   ```

   Adjust `-L` ports if `8000` / `8020` are already taken locally; see comments in that script.

2. In `.env` (see `.env.example`):

   - `FW_WHISPER_BACKEND=remote`
   - `FW_WHISPER_API_URL=http://host.docker.internal:8000` (or mapped ports)
   - `CHATTERBOX_API_URL=http://host.docker.internal:8020`
   - `FW_CHATTERBOX_SKIP_HEAVY_PROBE=1` if health checks should not load full models on the API container

3. Start the stack with the **cpu** profile (no local GPU containers), or **nvidia** if you also run GPU services locally — do not double-bind the same ports.

## Deliverables

Large dubbed `.mp4` / `.vtt` files should stay **out of git**; use `deliverables/` locally and submit via Drive/LMS as instructed in `deliverables/README.md`.
