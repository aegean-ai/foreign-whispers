#!/usr/bin/env python3
"""Optional **burned-in** Spanish subtitles + H.264 transcode for local preview only.

The Foreign Whispers **P5 stitch** stage (per course docs) is:

- **ffmpeg remux**: copy original **video** stream, replace **audio** with TTS.
- **WebVTT**: generated **alongside** the MP4 (``dubbed_captions/`` + ``GET /api/captions``).

That two-file output is what Notebook 7 and the Dubbing Studio verify. QuickTime on macOS
often refuses **AV1** in MP4; this script re-encodes to **H.264** and **draws** subtitles on
the frames for players that cannot load sidecar VTT.

Usage (from repo root, after stitch + captions exist)::

    uv run python scripts/burn_in_dubbed_preview.py \\
        --dubbed-mp4 pipeline_data/api/dubbed_videos/c-fb1074a/<Title>.mp4 \\
        --vtt pipeline_data/api/dubbed_captions/<Title>.vtt \\
        --out deliverables/GYQ5yGV_-Oc_dubbed_burnin_preview.mp4
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dubbed-mp4", type=Path, required=True, help="Dubbed MP4 from P5 (audio remux).")
    p.add_argument("--vtt", type=Path, required=True, help="Rolling WebVTT (same as dubbed_captions).")
    p.add_argument("--out", type=Path, required=True, help="Output MP4 path (H.264 + burned subs).")
    p.add_argument("--crf", type=int, default=23, help="libx264 CRF (default 23).")
    p.add_argument(
        "--preset",
        default="veryfast",
        help="libx264 preset (default veryfast; slower = better compression).",
    )
    args = p.parse_args()

    if not shutil.which("ffmpeg"):
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 1
    if not args.dubbed_mp4.is_file():
        print(f"Missing dubbed MP4: {args.dubbed_mp4}", file=sys.stderr)
        return 1
    if not args.vtt.is_file():
        print(f"Missing VTT: {args.vtt}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    vtt_abs = args.vtt.resolve()
    # ffmpeg subtitles filter: single-quoted path for special characters
    sub_path = str(vtt_abs).replace("'", r"'\''")
    vf = f"subtitles='{sub_path}':charenc=UTF-8:force_style='FontSize=20,Outline=2'"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(args.dubbed_mp4.resolve()),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        args.preset,
        "-crf",
        str(args.crf),
        "-c:a",
        "copy",
        str(args.out.resolve()),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout or "ffmpeg failed", file=sys.stderr)
        return proc.returncode
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
