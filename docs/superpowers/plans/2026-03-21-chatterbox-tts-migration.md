# Chatterbox TTS Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace XTTS v2 with Chatterbox (Resemble AI) as the TTS engine for the Foreign Whispers dubbing pipeline.

**Architecture:** Swap the XTTS Docker container for a Chatterbox TTS server (`travisvn/chatterbox-tts-api`). Rewrite the `XTTSClient` class in `tts_es.py` to call Chatterbox's OpenAI-compatible API. Keep `pyrubberband` post-processing alignment unchanged — Chatterbox has no speed parameter, so time-stretching remains a post-generation step. Use the multilingual model (`ChatterboxMultilingualTTS`) since the pipeline targets non-English languages.

**Tech Stack:** Chatterbox TTS (MIT license), `travisvn/chatterbox-tts-api` Docker image, Python `requests`, existing `pyrubberband` + `pydub` + `librosa` for post-processing.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `docker-compose.yml` | Modify | Replace `xtts-gpu` service with `chatterbox-gpu` |
| `tts_es.py` | Modify | Replace `XTTSClient` with `ChatterboxClient`, update env vars |
| `api/src/core/config.py` | Modify | Update env var names and defaults |
| `api/src/routers/tts.py` | Modify | Update env reference in comments (minimal) |
| `frontend/src/components/settings-dialog.tsx` | Modify | Rename "XTTS Speaker Embedding" to "Chatterbox" |
| `notebooks/tts_integration/tts_integration.ipynb` | Modify | Update references to XTTS |

---

### Task 1: Replace the TTS Docker Container

**Files:**
- Modify: `docker-compose.yml:28-57`

- [ ] **Step 1: Replace the `xtts-gpu` service with `chatterbox-gpu`**

Replace the entire `xtts-gpu` service block in `docker-compose.yml` with:

```yaml
  # ── TTS (Text-to-Speech) — Chatterbox on GPU ──────────────────────
  chatterbox-gpu:
    container_name: foreign-whispers-tts
    profiles: [nvidia]
    image: travisvn/chatterbox-tts-api:latest
    restart: unless-stopped
    shm_size: "8gb"
    ports:
      - "8020:8020"
    environment:
      - DEVICE=cuda
      - DEFAULT_MODEL=multilingual
      - PORT=8020
    volumes:
      - chatterbox-models:/app/models
      - ./pipeline_data/speakers:/app/voices
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

- [ ] **Step 2: Update the volumes section**

Replace the XTTS volumes with Chatterbox volumes:

```yaml
volumes:
  whisper-cache:
  chatterbox-models:
```

Remove `xtts-models` and `xtts-output`.

- [ ] **Step 3: Update the API environment variable**

In the `api` service, change:

```yaml
    environment:
      - CHATTERBOX_API_URL=http://localhost:8020
```

Remove `XTTS_API_URL`.

- [ ] **Step 4: Verify the container starts**

```bash
docker compose --profile nvidia pull chatterbox-gpu
docker compose --profile nvidia up -d chatterbox-gpu
# Wait for model download (first run takes a few minutes)
docker compose --profile nvidia logs -f chatterbox-gpu
```

Expected: the server logs "Uvicorn running on http://0.0.0.0:8020" after loading the multilingual model.

- [ ] **Step 5: Test the Chatterbox API**

```bash
curl -X POST http://localhost:8020/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "Hola mundo", "voice": "default"}' \
  --output /tmp/test_chatterbox.wav
file /tmp/test_chatterbox.wav
```

Expected: a valid WAV file.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: replace XTTS v2 container with Chatterbox TTS"
```

---

### Task 2: Rewrite the TTS Client

**Files:**
- Modify: `tts_es.py:15-101`

- [ ] **Step 1: Update the configuration constants**

Replace the XTTS config block (lines 15-18) with:

```python
# ── Chatterbox API configuration ─────────────────────────────────────
CHATTERBOX_API_URL = os.getenv("CHATTERBOX_API_URL", "http://localhost:8020")
CHATTERBOX_SPEAKER = os.getenv("CHATTERBOX_SPEAKER", "default")
CHATTERBOX_LANGUAGE = os.getenv("CHATTERBOX_LANGUAGE", "es")
```

- [ ] **Step 2: Replace `XTTSClient` with `ChatterboxClient`**

Replace the entire `XTTSClient` class (lines 34-100) with:

```python
class ChatterboxClient:
    """Thin HTTP client for the Chatterbox TTS API server (OpenAI-compatible)."""

    def __init__(self, base_url: str = CHATTERBOX_API_URL,
                 speaker: str = CHATTERBOX_SPEAKER,
                 language: str = CHATTERBOX_LANGUAGE):
        self.base_url = base_url.rstrip("/")
        self.speaker = speaker
        self.language = language

    def tts_to_file(self, text: str, file_path: str, **kwargs) -> None:
        """Synthesize *text* via the Chatterbox API and save the WAV to *file_path*.

        Long sentences are split into chunks of ≤200 chars at sentence
        boundaries to avoid timeouts on long inputs.
        """
        chunks = self._split_text(text) if len(text) > 200 else [text]
        wav_parts = []

        speaker = kwargs.get("speaker_wav", self.speaker)
        language = kwargs.get("language", self.language)

        for chunk in chunks:
            resp = requests.post(
                f"{self.base_url}/v1/audio/speech",
                json={
                    "input": chunk,
                    "voice": speaker,
                    "language": language,
                    "response_format": "wav",
                },
                timeout=(5, 60),
            )
            resp.raise_for_status()
            wav_parts.append(resp.content)

        if len(wav_parts) == 1:
            pathlib.Path(file_path).write_bytes(wav_parts[0])
        else:
            combined = AudioSegment.empty()
            for part in wav_parts:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                    tmp.write(part)
                    tmp.flush()
                    combined += AudioSegment.from_wav(tmp.name)
            combined.export(file_path, format="wav")

    @staticmethod
    def _split_text(text: str, max_len: int = 200) -> list[str]:
        """Split text at sentence boundaries to stay under max_len chars."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks, current = [], ""
        for s in sentences:
            if current and len(current) + len(s) + 1 > max_len:
                chunks.append(current.strip())
                current = s
            else:
                current = f"{current} {s}".strip() if current else s
        if current:
            chunks.append(current.strip())
        return chunks if chunks else [text]
```

Key differences from `XTTSClient`:
- Calls `/v1/audio/speech` (OpenAI-compatible) instead of `/tts_to_audio`
- Sends `input` (not `text`), `voice` (not `speaker_wav`), `language`
- Response is raw WAV bytes directly (not a JSON with a URL to fetch)
- `speaker_wav` kwarg still accepted for backward compatibility with the voice cloning flow

- [ ] **Step 3: Update `_make_tts_engine` to use ChatterboxClient**

Replace the `_make_tts_engine` function (lines 103-136) with:

```python
def _make_tts_engine():
    """Create TTS engine: Chatterbox API client if server is reachable, else local fallback."""
    try:
        r = requests.get(f"{CHATTERBOX_API_URL}/languages", timeout=5)
        if r.ok:
            client = ChatterboxClient()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                client.tts_to_file(text="prueba", file_path=tmp.name)
            print(f"[tts_es] Using Chatterbox GPU server at {CHATTERBOX_API_URL}")
            return client
    except Exception as exc:
        print(f"[tts_es] Chatterbox not available ({exc}), falling back to local Coqui")

    # Fallback: local Coqui TTS (for dev/test without Docker)
    import functools
    import torch
    from TTS.api import TTS as CoquiTTS
    _original_torch_load = torch.load
    @functools.wraps(_original_torch_load)
    def _patched_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return _original_torch_load(*args, **kwargs)
    torch.load = _patched_load
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[tts_es] Using local Coqui TTS on {device}")
    return CoquiTTS(model_name="tts_models/es/mai/tacotron2-DDC", progress_bar=False).to(device)
```

- [ ] **Step 4: Verify alignment code is untouched**

The `_postprocess_segment`, `_synced_segment_audio`, and `text_file_to_speech` functions remain unchanged — they work on WAV bytes regardless of which TTS engine produced them.

- [ ] **Step 5: Commit**

```bash
git add tts_es.py
git commit -m "feat: replace XTTSClient with ChatterboxClient"
```

---

### Task 3: Update API Configuration

**Files:**
- Modify: `api/src/core/config.py:86-87`

- [ ] **Step 1: Rename the config field**

In `api/src/core/config.py`, replace:

```python
    # External service URLs
    xtts_api_url: str = "http://localhost:8020"
```

with:

```python
    # External service URLs
    chatterbox_api_url: str = "http://localhost:8020"
```

- [ ] **Step 2: Update the TTS model dir default**

Replace:

```python
    tts_model_dir: str = "xtts-v2"
```

with:

```python
    tts_model_dir: str = "chatterbox"
```

- [ ] **Step 3: Commit**

```bash
git add api/src/core/config.py
git commit -m "refactor: rename xtts config to chatterbox"
```

---

### Task 4: Update Frontend Labels

**Files:**
- Modify: `frontend/src/components/settings-dialog.tsx:143`

- [ ] **Step 1: Update the voice cloning method label**

In `settings-dialog.tsx`, replace:

```typescript
const VOICE_CLONING_METHODS = [
  { value: "xtts", label: "XTTS Speaker Embedding", description: "Clone from reference audio via XTTS v2" },
];
```

with:

```typescript
const VOICE_CLONING_METHODS = [
  { value: "chatterbox", label: "Chatterbox", description: "Voice cloning via Chatterbox (Resemble AI)" },
];
```

- [ ] **Step 2: Update the TTS engine display**

In the `TTSSettings` function, replace the TTS engine label:

```typescript
<span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">XTTS v2</span>
```

with:

```typescript
<span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">Chatterbox</span>
```

- [ ] **Step 3: Build and verify**

```bash
docker compose --profile nvidia build frontend
docker compose --profile nvidia up -d frontend
```

Open http://localhost:8501, click Settings gear icon, go to TTS — should show "Chatterbox".

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings-dialog.tsx
git commit -m "refactor: update TTS labels from XTTS to Chatterbox"
```

---

### Task 5: Update Pipeline Table Configuration Column

**Files:**
- Modify: `frontend/src/components/pipeline-table.tsx:102`

- [ ] **Step 1: Update the TTS config display**

In the `getConfig` function, the TTS case currently mentions "XTTS v2" as a fallback label. Update:

```typescript
      case "tts": {
        const parts: string[] = [];
        if (settings.dubbing.includes("aligned")) parts.push("Aligned");
        else parts.push("Baseline");
        if (settings.voiceCloning.length > 0) parts.push(settings.voiceCloning.join(", "));
        if (settings.diarization.length > 0) parts.push(settings.diarization.join(", "));
        return parts.join(" + ") || "Chatterbox";
      }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/pipeline-table.tsx
git commit -m "refactor: update pipeline table TTS label to Chatterbox"
```

---

### Task 6: Upload Speaker Voices to Chatterbox

**Files:**
- No code changes — operational task

The Chatterbox server manages voices via its `/voices` API. The existing reference WAVs in `pipeline_data/speakers/` need to be registered.

- [ ] **Step 1: Check the voice library**

```bash
curl http://localhost:8020/voices | python3 -m json.tool
```

- [ ] **Step 2: Upload the default speaker**

```bash
curl -X POST http://localhost:8020/voices \
  -F "name=default" \
  -F "file=@pipeline_data/speakers/default.wav"
```

- [ ] **Step 3: Upload language-specific speakers**

```bash
for lang_dir in pipeline_data/speakers/*/; do
  lang=$(basename "$lang_dir")
  for wav in "$lang_dir"*.wav; do
    name="${lang}_$(basename "$wav" .wav)"
    curl -X POST http://localhost:8020/voices \
      -F "name=$name" \
      -F "file=@$wav"
  done
done
```

- [ ] **Step 4: Verify voices are registered**

```bash
curl http://localhost:8020/voices | python3 -m json.tool
```

- [ ] **Step 5: Document the voice naming convention**

Voices are named `{lang}_{stem}` (e.g. `es_default`, `fr_default`). The `ChatterboxClient` passes the voice name directly to the `voice` field in the API request.

---

### Task 7: End-to-End Validation

**Files:**
- No code changes — integration test

- [ ] **Step 1: Rebuild and restart all services**

```bash
docker compose --profile nvidia down
docker compose --profile nvidia build api
docker compose --profile nvidia up -d
```

- [ ] **Step 2: Run the pipeline via the API**

```bash
# Download
curl -X POST http://localhost:8080/api/download \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=GYQ5yGV_-Oc"}'

# Transcribe
curl -X POST http://localhost:8080/api/transcribe/GYQ5yGV_-Oc

# Translate
curl -X POST "http://localhost:8080/api/translate/GYQ5yGV_-Oc?target_language=es"

# TTS (baseline)
curl -X POST "http://localhost:8080/api/tts/GYQ5yGV_-Oc?config=c-fb1074a&alignment=false"

# TTS (aligned)
curl -X POST "http://localhost:8080/api/tts/GYQ5yGV_-Oc?config=c-86ab861&alignment=true"

# Stitch
curl -X POST "http://localhost:8080/api/stitch/GYQ5yGV_-Oc?config=c-fb1074a"
```

- [ ] **Step 3: Verify audio quality**

Listen to the output WAV in `pipeline_data/api/tts_audio/chatterbox/c-fb1074a/` and compare with previous XTTS output.

- [ ] **Step 4: Run the end-to-end notebook**

```bash
cd notebooks/pipeline_end_to_end
uv run jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.timeout=600 \
  --ExecutePreprocessor.kernel_name=foreign-whispers \
  pipeline_end_to_end.ipynb --output /tmp/e2e_chatterbox.ipynb
```

- [ ] **Step 5: Run the pipeline from the frontend**

Open http://localhost:8501, select the Strait of Hormuz video, click Start Pipeline. Verify all stages complete and the dubbed video plays.

- [ ] **Step 6: Commit any remaining fixes**

```bash
git add -A
git commit -m "chore: Chatterbox TTS migration complete"
```

---

## Migration Checklist

| # | Item | How to verify |
|---|------|---------------|
| 1 | Chatterbox container starts and serves `/v1/audio/speech` | `curl http://localhost:8020/v1/audio/speech -d '{"input":"test","voice":"default"}'` returns WAV |
| 2 | `ChatterboxClient.tts_to_file()` produces valid WAV | Run single-segment TTS from Python |
| 3 | Alignment still works | Compare baseline vs aligned WAV durations — aligned should match source timing |
| 4 | Voice cloning works | Pass `speaker_wav=es_default` and verify voice similarity |
| 5 | Frontend shows "Chatterbox" | Settings dialog TTS section |
| 6 | End-to-end pipeline completes | All 5 stages pass in the frontend |
| 7 | No XTTS references remain | `grep -r "xtts\|XTTS" --include="*.py" --include="*.ts" --include="*.yml"` returns nothing relevant |

## Rollback

If Chatterbox quality is unsatisfactory, revert the `docker-compose.yml` and `tts_es.py` changes. The alignment and post-processing code is engine-agnostic — only the client class and container definition change.
