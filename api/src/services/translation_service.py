"""HTTP-agnostic service wrapping translate_en_to_es.py functions."""

import copy
import importlib as _importlib
import pathlib
from pathlib import Path


def _get_translate_module():
    return _importlib.import_module("translate_en_to_es")


def download_and_install_package(from_code: str, to_code: str):
    return _get_translate_module().download_and_install_package(from_code, to_code)


def translate_sentence(text: str, from_code: str, to_code: str):
    return _get_translate_module().translate_sentence(text, from_code, to_code)


class TranslationService:
    """Thin wrapper around argostranslate-based translation.

    Takes *ui_dir* via constructor so the caller controls file paths.
    """

    def __init__(self, ui_dir: Path) -> None:
        self.ui_dir = ui_dir

    def install_language_pack(self, from_code: str, to_code: str) -> None:
        """Download and install the Argos Translate language pack."""
        download_and_install_package(from_code, to_code)

    def translate_sentence(self, text: str, from_code: str, to_code: str) -> str:
        """Translate a single sentence."""
        return translate_sentence(text, from_code, to_code)

    def translate_transcript(self, transcript: dict, from_code: str, to_code: str) -> dict:
        """Translate all segments and full text in a transcript dict.

        Returns a deep copy; the original is not mutated.
        """
        result = copy.deepcopy(transcript)
        for segment in result.get("segments", []):
            segment["text"] = translate_sentence(segment["text"], from_code, to_code)
        result["text"] = translate_sentence(result.get("text", ""), from_code, to_code)
        result["language"] = to_code
        return result

    @staticmethod
    def title_for_video_id(video_id: str, search_dir: pathlib.Path) -> str | None:
        """Find a title by scanning *search_dir* for JSON files."""
        for f in search_dir.glob("*.json"):
            return f.stem
        return None
