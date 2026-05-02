## Context

The TTS integration notebook describes a `speaker_wav` **query parameter** on `POST /api/tts/{video_id}` and using `resolve_speaker_wav()` for stable speaker → reference WAV mapping.

## Current behaviour

The API exposes `per_speaker_voice` (boolean). `foreign_whispers.voice_resolution.resolve_speaker_wav()` is implemented with tests, but the TTS engine builds a speaker→WAV map by **round-robin** over files under `pipeline_data/speakers/` rather than calling `resolve_speaker_wav` per `SPEAKER_xx`.

## Proposal (pick one)

1. Add optional `speaker_wav` query param as a global override for testing; **or**
2. Wire `resolve_speaker_wav(settings.speakers_dir, target_lang, speaker_id)` into the per-segment metadata path so notebook and runtime match.

## Acceptance

- Contract documented in OpenAPI / router docstrings.
- `tests/test_tts_router.py` (or similar) covers the new parameter if added.
