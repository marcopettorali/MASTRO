"""audio_intent — MOSAIC local service (adapted from the c2ct audio pipeline).

Standard MOSAIC local-service contract:
  reads  MOSAIC_INPUT_FILE   (JSON, must contain "transcribed_text")
  writes MOSAIC_OUTPUT_FILE  (JSON, adds detected intent fields)

Third and final stage: offline intent classification of the transcribed
command using purely lexical/statistical methods. Pure Python + stdlib.
"""

import json
import os
from pathlib import Path

from lib.worker_core import classify_intent

# ── MOSAIC standard path setup (C2TC_* kept as fallback for portability) ──────
INPUT_FILE = Path(os.environ.get("MOSAIC_INPUT_FILE")
                  or os.environ.get("C2TC_INPUT_FILE", "input.json"))
OUTPUT_FILE = Path(os.environ.get("MOSAIC_OUTPUT_FILE")
                   or os.environ.get("C2TC_OUTPUT_FILE", "output.json"))


def main() -> None:
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {"value_1": data}
    result = classify_intent(data)
    OUTPUT_FILE.write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
