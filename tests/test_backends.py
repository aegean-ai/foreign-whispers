import pytest
from foreign_whispers.backends import DurationAwareTTSBackend


def test_backend_is_abstract():
    with pytest.raises(TypeError):
        DurationAwareTTSBackend()


def test_concrete_subclass_can_be_instantiated():
    class MockBackend(DurationAwareTTSBackend):
        def synthesize(self, text, output_path, duration_hint_s=None,
                       pause_budget_s=None, max_stretch_factor=1.4) -> float:
            return 1.0

    b = MockBackend()
    assert b.synthesize("hello", "/tmp/out.wav") == 1.0


def test_repr():
    class MockBackend(DurationAwareTTSBackend):
        def synthesize(self, text, output_path, duration_hint_s=None,
                       pause_budget_s=None, max_stretch_factor=1.4) -> float:
            return 0.0
    assert "MockBackend" in repr(MockBackend())
