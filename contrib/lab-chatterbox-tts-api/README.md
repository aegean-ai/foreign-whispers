# Lab / cluster overrides for Chatterbox TTS API

These files are **not** part of the Foreign Whispers Python package. They are copies of edits we applied on a **separate clone** of [chatterbox-tts-api](https://github.com/travisvn/chatterbox-tts-api) running on a **GPU lab host**, while the course stack (API + frontend + orchestration) ran on a **CPU-only** machine with SSH tunnels.

## Why this folder exists

- **Torch / CUDA:** `pyproject.toml` pins overrides for PyTorch CUDA 12.8 wheels (Blackwell-class GPUs) and a multilingual Chatterbox fork, matching what worked on our cluster image.
- **WAV encoding:** `speech.py` writes TTS output via a **temporary `.wav` file** then reads bytes — some `torchaudio` / TorchCodec builds cannot encode directly to `BytesIO` reliably.
- **Config:** `config.py` warns if `ffmpeg` is missing on the host (needed for some audio paths).

Files in this folder map to upstream paths as follows:

| Here | Upstream (typical) |
|------|---------------------|
| `config.py` | `app/config.py` |
| `speech.py` | `app/api/endpoints/speech.py` |
| `pyproject.toml` | `pyproject.toml` |

## How to use

1. Clone `chatterbox-tts-api` on the GPU server into e.g. `~/chatterbox-tts-api`.
2. Diff or copy files from this directory over the upstream versions as needed.
3. Start the server with `scripts/remote-cluster/start-chatterbox.sh` from **this** repo (set `CHATTERBOX_DIR`).

Upstream owns licensing and versioning; treat this directory as **documentation of our deployment**, not a submodule.
