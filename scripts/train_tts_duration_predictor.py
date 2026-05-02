#!/usr/bin/env python3
"""Train a lightweight Ridge predictor for TTS segment duration from text features.

Supervision comes from `{stem}.align.json` sidecars written next to synthesized WAVs
when TTS alignment is enabled. Each segment entry includes ``text`` and
``raw_duration_s`` (measured WAV length before/after temporal fit — see ``tts_engine``).

Example:

    uv sync --group dev
    uv run python scripts/train_tts_duration_predictor.py \\
      --align-root pipeline_data/api/tts_audio \\
      --out foreign_whispers/tts_duration_ridge.json

At runtime, set ``FW_TTS_DURATION_MODEL`` to that JSON path or place the same file next to
``foreign_whispers/alignment.py`` as ``tts_duration_ridge.json`` (see ``alignment.py``).

Requires: dependency group ``dev`` (scikit-learn).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from pathlib import Path

from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


def _count_syllables(text: str) -> int:
    """Must stay in sync with ``foreign_whispers.alignment._count_syllables``."""

    nfkd = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    clusters = re.findall(r"[aeiou]+", ascii_text)
    return max(1, len(clusters))


def _iter_align_paths(root: Path) -> list[Path]:
    return sorted(root.rglob("*.align.json"))


def _load_rows(paths: list[Path]) -> tuple[list[list[float]], list[float]]:
    """Build X (chars, syllables, words) and y (seconds) from sidecars."""

    xs: list[list[float]] = []
    ys: list[float] = []
    for p in paths:
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for seg in data.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            text = str(seg.get("text", "")).strip()
            rd = seg.get("raw_duration_s")
            try:
                y = float(rd)
            except (TypeError, ValueError):
                continue
            if not text or y <= 0.0 or y > 600.0:
                continue
            n_chars = float(len(text))
            n_syl = float(_count_syllables(text))
            n_words = float(max(1, len(text.split())))
            xs.append([n_chars, n_syl, n_words])
            ys.append(y)
    return xs, ys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--align-root",
        type=Path,
        default=Path("pipeline_data/api/tts_audio"),
        help="Root directory to recurse for *.align.json (default: pipeline_data/api/tts_audio)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("foreign_whispers/tts_duration_ridge.json"),
        help="Output JSON artifact for alignment.py (default: foreign_whispers/tts_duration_ridge.json)",
    )
    ap.add_argument(
        "--alpha",
        type=float,
        default=1.0,
        help="Ridge alpha (default: 1.0)",
    )
    ap.add_argument(
        "--min-samples",
        type=int,
        default=40,
        help="Minimum labelled segments required (default: 40)",
    )
    ap.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Hold-out fraction for MAE / RMSE report (default: 0.2)",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Random seed for train/test split",
    )
    args = ap.parse_args()

    root: Path = args.align_root.expanduser().resolve()
    paths = _iter_align_paths(root)
    if not paths:
        print(f"No *.align.json under {root}. Run TTS with alignment enabled first.")
        return 2

    X_raw, y = _load_rows(paths)
    if len(y) < args.min_samples:
        print(
            f"Too few labelled segments: {len(y)} (< {args.min_samples}). "
            "Generate more *.align.json by running dubbed TTS.",
        )
        # Diagnose all-zero raw_duration_s rows (Chatterbox / network failures).
        synth_fail = synth_ok = zero_raw = total_segs = 0
        for p in paths:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            synth_fail += int(data.get("tts_raw_synthesis_failed") or 0)
            synth_ok += int(data.get("tts_raw_synthesis_ok") or 0)
            for seg in data.get("segments") or []:
                if not isinstance(seg, dict):
                    continue
                total_segs += 1
                try:
                    rd = float(seg.get("raw_duration_s", 0) or 0)
                except (TypeError, ValueError):
                    rd = 0.0
                if rd <= 0.0:
                    zero_raw += 1
        if synth_fail > 0 and synth_ok == 0 and total_segs > 0:
            print(
                "Sidecars report tts_raw_synthesis_failed>0 but no successes — synthesis never returned audio. "
                "Check Docker logs on `foreign-whispers-api`, SSH tunnel ports, CHATTERBOX_API_URL, "
                "and FW_CHATTERBOX_HTTP_READ_TIMEOUT (slow remote hosts)."
            )
        elif total_segs > 5 and zero_raw >= total_segs - 2:
            print(
                "Most segment rows have raw_duration_s≤0 — the trainer ignores those as labels. "
                "Fix upstream TTS/Chatterbox before re-running.",
            )
        return 3

    X_train, X_test, y_train, y_test = train_test_split(
        X_raw,
        y,
        test_size=args.test_size,
        random_state=args.seed,
    )

    scaler = StandardScaler()
    scaler.fit(X_train)
    scaler.scale_[scaler.scale_ < 1e-9] = 1.0
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = Ridge(alpha=args.alpha)
    model.fit(X_train_s, y_train)

    pred_test = model.predict(X_test_s)
    mae = mean_absolute_error(y_test, pred_test)
    rmse = math.sqrt(mean_squared_error(y_test, pred_test))
    print(
        f"Trained Ridge on {len(y_train)} segments; hold-out ({len(y_test)}): MAE={mae:.4f}s RMSE={rmse:.4f}s "
        f"(from {len(paths)} sidecars)",
    )

    artifact = {
        "version": 1,
        "kind": "ridge_standard_scaled",
        "feature_names": ["chars", "syllables", "words"],
        "intercept": float(model.intercept_),
        "coef": [float(c) for c in model.coef_.ravel()],
        "mean": [float(x) for x in scaler.mean_],
        "scale": [float(s) for s in scaler.scale_],
        "min_duration_s": 0.05,
        "max_duration_s": 600.0,
        "training_segments": len(y),
        "align_files": len(paths),
    }

    out: Path = args.out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
