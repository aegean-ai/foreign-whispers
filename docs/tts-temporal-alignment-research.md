# TTS Temporal Alignment for Video Dubbing — Research Guide

This document surveys the academic literature on temporal alignment for automated video dubbing. It accompanies the `alignment_integration` notebook and provides research context for the student tasks defined there.

## The Core Problem

Dubbing is constrained generation under a timing budget. A 3-second English phrase might take 5 seconds in Spanish. The question is: where in the pipeline should you solve this?

| Approach | Where it acts | Trade-off |
|----------|--------------|-----------|
| Post-hoc time-stretching | After TTS | Fast but distorts speech beyond ±25% |
| Duration-controlled TTS | During TTS | Natural audio but requires model support |
| Isochronous translation | Before TTS | Best quality but hardest to implement |

The field has converged on a practical sweet spot: **length-controlled translation + mild time-stretching (≤15%)**. Duration-controlled TTS generation is the next frontier.

---

## Literature Survey

### 1. Isochronous / Isometric Machine Translation

The core idea: modify the **translation** step to produce target text whose spoken duration approximately matches the source.

| Paper | Year | Venue | Key Contribution |
|-------|------|-------|------------------|
| Lakew, Federico et al. — *Isometric MT: Neural MT for Automatic Dubbing* | 2022 | ICASSP | Self-learning approach: transformer generates outputs matching source character/token length. Uses length compliance reward. |
| Lakew, Federico et al. — *Isochrony-Aware Neural MT for Automatic Dubbing* | 2021 | arXiv 2112.08548 | Both implicit (data augmentation with pauses) and explicit (segment-level length tags) approaches to integrate timing constraints into NMT. |
| Pal et al. — *Improving Isochronous MT with Target Factors and Auxiliary Counters* | 2023 | Interspeech | Target factors predict durations jointly with phoneme sequences; auxiliary counters track remaining time budget during decoding. |
| Wu, Guo, Tan et al. — *VideoDubber: MT with Speech-Aware Length Control* | 2023 | AAAI | Controls speech length (not just character count) by guiding each word prediction with its own speech duration plus remaining duration budget. |
| Lakew, Federico et al. — *MT Verbosity Control for Automatic Dubbing* | 2022 | ICASSP | Systematic comparison of verbosity control methods; extrinsic evaluation on actual dubbed clips. |
| Subramanian et al. — *Length Aware Speech Translation for Video Dubbing* | 2025 | Interspeech | Recent work on speech translation with explicit duration awareness. |

**Key insight**: The field moved from controlling character/word count (*isometric*) to controlling actual speech duration (*isochronous*), since different languages have different phoneme durations.

### 2. Prosody-Aligned TTS for Dubbing

| Paper | Year | Venue | Key Contribution |
|-------|------|-------|------------------|
| Federico et al. — *Evaluating and Optimizing Prosodic Alignment for Automatic Dubbing* | 2020 | Interspeech | Foundational work on prosodic alignment. Distinguishes on-screen (lip-sync required) vs off-screen (relaxed) isochrony. |
| Virkar, Federico et al. — *Prosodic Alignment for Off-Screen Automatic Dubbing* | 2022 | arXiv 2204.02530 | Off-screen speech: lip-sync constraints relaxed but naturalness still needed. |
| Effendi, Virkar et al. — *Duration Modeling of Neural TTS for Automatic Dubbing* | 2022 | ICASSP | Novel duration models that both predict and control TTS duration. Improves prosodic alignment for both slow and fast speaking rates. |
| *CrossVoice: Crosslingual Prosody Preserving Cascade-S2ST* | 2024 | arXiv 2406.00021 | Cascade ASR+MT+TTS evaluated on cross-lingual prosody preservation. |
| *FCConDubber: Fine And Coarse Grained Prosody Alignment for Expressive Video Dubbing* | 2024 | IEEE | Contrastive speech-motion pre-training for fine-grained temporal prosodic alignment. |

### 3. Duration-Controlled TTS

Two paradigms for fitting TTS into a time window:

**A. Post-hoc time-stretching** (current Foreign Whispers approach):
- WSOLA (Waveform-Similarity Overlap-Add) — superior to TD-PSOLA for vocal stretching
- Rubber band library — good up to ~15% stretch
- VideoDubber insight: only stretch **vowel** durations, not consonants, for more natural results

**B. Duration-controlled generation** (preferred):

| Paper | Year | Key Contribution |
|-------|------|------------------|
| Microsoft Research — *Total-Duration-Aware Duration Modeling for TTS* | 2024 | Duration model takes total target duration as input. Predicts phoneme durations conditioned on desired total length. (arXiv 2406.04281) |
| *IndexTTS2* | 2025 | Autoregressive zero-shot TTS with explicit duration control and emotional expressivity. |
| Choi, Kim et al. — *Dub-S2ST: Textless S2ST for Seamless Dubbing* | 2025 | Discrete diffusion-based translation with explicit duration control. Unit-based speed adaptation guides translation to match source speaking rate without text. (EMNLP 2025) |

### 4. End-to-End Systems

| System | Organization | Year | Approach |
|--------|-------------|------|----------|
| **SeamlessM4T v2 / SeamlessExpressive** | Meta FAIR | 2023 | Foundation model for multilingual multimodal translation. Preserves vocal style and prosody across 100+ languages. |
| **Translatotron 3** | Google | 2023 | S2ST from monolingual data. Preserves pauses, speaking rates, speaker identity. |

### 5. Open-Source Dubbing Pipelines

| Tool | Pipeline | Notes |
|------|----------|-------|
| **[open-dubbing](https://github.com/Softcatala/open-dubbing)** | Faster-Whisper, NLLB-200, Coqui/MMS/Edge TTS | Most complete open-source system. |
| **[SoniTranslate](https://github.com/R3gm/SoniTranslate)** | Whisper, Translation, TTS | Synchronized translation with multiple output formats. |
| **Meta Seamless** | End-to-end S2ST | Can serve as translation backbone. 100+ languages. |

---

## Research Directions for Students

These connect directly to the tasks in the `alignment_integration` notebook:

### Duration Prediction (Task 1)

The 15 chars/second heuristic is the weakest link. **Syllable count is a tighter proxy for Spanish**: Spanish phoneme duration is highly regular (~75 ms/syllable), while character count is distorted by accents, digraphs, and punctuation. Replacing the character-count heuristic with a syllable counter (e.g., `pyphen` or a simple vowel-cluster count) would improve `decide_action()` accuracy without any model change.

### Duration-Aware Translation (Task 2)

LLM re-ranking is a prompt-engineering approximation of isochronous MT. For segments where `decide_action()` returns `REQUEST_SHORTER`, an LLM generates shorter alternatives and a deterministic scorer picks the best fit by duration. This avoids fine-tuning entirely. For a deeper approach, fine-tune NLLB-200 with length tags per Lakew et al. 2021.

### Global Optimization (Task 3)

The greedy optimizer treats silence as a resource that can be borrowed. More sophisticated approaches (DP, ILP) can allocate this resource globally. An important refinement: **on-screen speech** (speaker's lips visible) requires tight isochrony (±100 ms), while **off-screen narration** allows ~300 ms of overflow (Federico et al. 2020). 60 Minutes interviews are predominantly off-screen, so selective thresholds would eliminate the most jarring sync failures.

### Evaluation (Task 4)

The sidecar `.align.json` files written alongside each WAV provide per-segment ground truth for evaluation. Compare baseline (`FW_ALIGNMENT=off`) vs aligned runs using `clip_evaluation_report()`. For richer evaluation, consider round-trip intelligibility (TTS → STT → compare) and embedding-based semantic fidelity.

---

## References

1. Lakew et al. "Isometric MT for Automatic Dubbing" ICASSP 2022. arXiv:2112.08682
2. Lakew et al. "Isochrony-Aware NMT for Automatic Dubbing" 2021. arXiv:2112.08548
3. Pal et al. "Improving Isochronous MT with Target Factors" Interspeech 2023
4. Wu et al. "VideoDubber: MT with Speech-Aware Length Control" AAAI 2023
5. Federico et al. "Evaluating Prosodic Alignment for Automatic Dubbing" Interspeech 2020
6. Virkar et al. "Prosodic Alignment for Off-Screen Automatic Dubbing" 2022. arXiv:2204.02530
7. Effendi et al. "Duration Modeling of Neural TTS for Automatic Dubbing" ICASSP 2022
8. Microsoft Research. "Total-Duration-Aware Duration Modeling for TTS" 2024. arXiv:2406.04281
9. Choi, Kim et al. "Dub-S2ST: Textless S2ST for Seamless Dubbing" EMNLP 2025
10. Meta FAIR. "Seamless: Multilingual Expressive and Streaming Speech Translation" 2023. arXiv:2312.05187
11. Softcatala. "open-dubbing" GitHub. https://github.com/Softcatala/open-dubbing
