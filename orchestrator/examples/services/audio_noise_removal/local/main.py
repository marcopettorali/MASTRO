"""audio_noise_removal — MOSAIC local service (adapted from the c2ct audio pipeline).

Standard MOSAIC local-service contract:
  reads  MOSAIC_INPUT_FILE   (JSON, must contain base-64 WAV in "audio_b64")
  writes MOSAIC_OUTPUT_FILE  (JSON, denoised audio + forwarded fields)

First stage of the speech pipeline: a Wiener-style noise suppression filter
cleans the recorded audio before it is sent downstream for transcription.
Pure Python + stdlib, so the CPU cost scales O(n) with the audio duration —
this is what makes a node saturate under the ramp traffic generator.

Load-control knob (experiment extension, default keeps behaviour identical):
  cpu_scale  int  repeat the denoise pass this many times (default 1).
"""

import json
import os
from pathlib import Path

from lib.worker_core import remove_background_noise

# ── MOSAIC standard path setup (C2TC_* kept as fallback for portability) ──────
INPUT_FILE = Path(os.environ.get("MOSAIC_INPUT_FILE")
                  or os.environ.get("C2TC_INPUT_FILE", "input.json"))
OUTPUT_FILE = Path(os.environ.get("MOSAIC_OUTPUT_FILE")
                   or os.environ.get("C2TC_OUTPUT_FILE", "output.json"))


def main() -> None:
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {"value_1": data}
    result = remove_background_noise(data)
    OUTPUT_FILE.write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
