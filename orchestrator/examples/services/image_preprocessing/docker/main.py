"""image_preprocessing — MOSAIC docker service (ported from the c2ct/PROMAX video pipeline).

Standard MOSAIC docker-service contract (see runtime_code/lib/service_exec.py
get_runtime_env_for_docker_step): the step dir is mounted at /data and the runtime sets
  MOSAIC_INPUT_FILE  = /data/input.json   (JSON, base-64 image in "image_b64")
  MOSAIC_OUTPUT_FILE = /data/output.json  (JSON, adds "tiles", …)
The original PROMAX entry point read C2TC_INPUT_FILE/C2TC_OUTPUT_FILE; this port honours
MOSAIC_* first and falls back to C2TC_* for portability. The algorithm (lib/worker_core.py)
is copied VERBATIM from PROMAX — nothing about the preprocessing changes.

First stage of the video pipeline: decode → per-channel histogram equalisation → unsharp
sharpening → multi-scale overlapping tiling (scales 0.5/1.0/1.5) → 640×640 tiles → per-tile
quality metrics → JPEG base-64. Fully offline, no network calls.
"""

import json
import os
from pathlib import Path

from lib.worker_core import preprocess_image

# ── MOSAIC standard path setup (C2TC_* kept as fallback for portability) ──────
WORK_DIR = Path(os.environ.get("MOSAIC_WORK_DIR")
                or os.environ.get("C2TC_WORK_DIR", "."))
INPUT_FILE = Path(os.environ.get("MOSAIC_INPUT_FILE")
                  or os.environ.get("C2TC_INPUT_FILE", WORK_DIR / "input.json"))
OUTPUT_FILE = Path(os.environ.get("MOSAIC_OUTPUT_FILE")
                   or os.environ.get("C2TC_OUTPUT_FILE", WORK_DIR / "output.json"))


def main() -> None:
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        data = {"value_1": data}
    result = preprocess_image(data)
    OUTPUT_FILE.write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
