# Foreign Whispers Final Project

## Overview

This is the final project of CS6613, extends the Foreign Whispers dubbing pipeline with improvements to diarization, TTS voice handling, alignment, and debugging.

Repository PR: https://github.com/aegean-ai/foreign-whispers/pull/21

Demo video: 

https://drive.google.com/file/d/1Ti9IgyVtEtTcYWwTNzKGCZaGAqub9qUW/view?usp=sharing

https://drive.google.com/file/d/109dDANLAEYYFgn6FuBSYYzQwuiQAAt6Z/view?usp=sharing

https://drive.google.com/file/d/1YWC9-sLW485_Tg3OAPxxZ6fwuQZHvD67/view?usp=sharing

https://drive.google.com/file/d/1Wt49Sdo77eQW_jB-Wnij3PQYmu8Oqy62/view?usp=sharing


## What I changed

### 1. Diarization speaker assignment
- Implemented speaker assignment logic so transcript segments can be labeled by speaker.
- Fixed behavior for empty diarization results by defaulting to `SPEAKER_00`.
- Ensured the implementation does not mutate the input segments.

### 2. Speaker-aware TTS voice resolution
- Added speaker WAV resolution with fallback logic:
  - `<language>/<speaker_id>.wav`
  - `<language>/default.wav`
  - `default.wav`
- Added support for passing resolved speaker reference voices through the API layer.

### 3. TTS API and service updates
- Updated the TTS endpoint to return resolved `speaker_wav`.
- Added support for per-speaker voice mapping in the TTS pipeline.
- Improved debugging information for TTS generation.

### 4. TTS alignment and timing improvements
- Added segment cleaning before synthesis.
- Added merging of incomplete neighboring subtitle segments before TTS.
- Added failure/debug reporting for synthesized segments.
- Investigated silence issues and timing mismatch between generated audio and target windows.

### 5. Alignment improvements
- Implemented beam-search / DP-based alignment logic in `alignment.py`.
- Added a more duration-aware alignment strategy compared to a simple greedy scheduler.

### 6. Debugging and analysis
- Added reporting for TTS failures and heavily padded segments.
- Investigated cases where dubbed output had silence or unnatural pacing.
- Identified that many silence issues came from timing mismatch and padding rather than total TTS failure.

## Files changed

Examples of key files modified:
- `foreign_whispers/diarization.py`
- `foreign_whispers/voice_resolution.py`
- `foreign_whispers/alignment.py`
- `api/src/routers/tts.py`
- `api/src/services/tts_service.py`
- `api/src/services/tts_engine.py`
- `api/src/core/config.py`

## Main issues discovered and solved

### Silence in dubbed output
The silence was caused by two main problems:
- some TTS calls failed on short or malformed subtitle fragments
- many successful TTS segments were much shorter than their target timing windows, causing heavy silence padding

### Inhuman sounding audio
Some successful segments sounded unnatural because:
- segments were overly compressed or stretched to fit timing windows
- translations were sometimes awkward or fragmented
- subtitle segmentation was not ideal for TTS

## What I learned

- Diarization labels alone are not enough; segmentation quality strongly affects TTS quality.
- TTS failures are often caused by short, broken subtitle fragments rather than obviously bad sentences.
- Alignment must match the same segmentation used by TTS, otherwise timing decisions become unreliable.
- Debug files and per-segment reporting are very useful for finding the real cause of silence.
