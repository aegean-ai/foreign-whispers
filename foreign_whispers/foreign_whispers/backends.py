"""Extended TTS interface with soft duration targets.

Extracted from notebooks/foreign_whispers_pipeline.ipynb (M3-align).
No external dependencies — stdlib only (abc).

Backends in api/src/inference/ may subclass DurationAwareTTSBackend to carry
alignment intent before waveform generation starts.  Backends that have no
prosody control should still satisfy the interface; the caller handles
post-synthesis time-stretching as a bounded fallback.
"""
import abc


class DurationAwareTTSBackend(abc.ABC):
    """Abstract TTS backend that accepts optional alignment metadata."""

    @abc.abstractmethod
    def synthesize(
        self,
        text:               str,
        output_path:        str,
        duration_hint_s:    float | None = None,
        pause_budget_s:     float | None = None,
        max_stretch_factor: float        = 1.4,
    ) -> float:
        """Synthesize *text* to *output_path* and return actual duration in seconds.

        Args:
            text: Text to synthesize.
            output_path: Destination WAV path.
            duration_hint_s: Soft target duration; backends may ignore if they
                             have no prosody control.
            pause_budget_s: Silence the backend may insert at natural boundaries.
            max_stretch_factor: Caller's safety bound for post-synthesis stretching.

        Returns:
            Actual synthesized audio duration in seconds.
        """

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"
