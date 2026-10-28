"""audio_transcription — MOSAIC local service (adapted from the c2ct audio pipeline).

Standard MOSAIC local-service contract:
  reads  MOSAIC_INPUT_FILE   (JSON, base-64 WAV in "audio_b64")
  writes MOSAIC_OUTPUT_FILE  (JSON, adds "transcribed_text")

Second stage: offline speech-to-text. If the Vosk engine and a model are
available (env VOSK_MODEL_PATH), real recognition is performed; otherwise the
service falls back to a deterministic CPU-bound transcriber that does work
proportional to the audio length and returns the phrase carried in the
payload. This keeps the pipeline runnable on any node without per-node model
provisioning, while preserving realistic per-job CPU cost for the experiments.
"""

import json
import os
from pathlib import Path

from lib.worker_core import transcribe

# ── MOSAIC standard path setup (C2TC_* kept as fallback for portability) ──────
INPUT_FILE = Path(os.environ.get("MOSAIC_INPUT_FILE")
                  or os.environ.get("C2TC_INPUT_FILE", "input.json"))
OUTPUT_FILE = Path(os.environ.get("MOSAIC_OUTPUT_FILE")
                   or os.environ.get("C2TC_OUTPUT_FILE", "output.json"))


def main() -> None:
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {"value_1": data}
    result = transcribe(data)
    OUTPUT_FILE.write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
