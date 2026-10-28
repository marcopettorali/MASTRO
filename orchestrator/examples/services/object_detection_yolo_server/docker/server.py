"""Persistent YOLOv8s model server (video pipeline).

Loads the YOLO model ONCE at startup ("prewarm"), then serves per-job detection requests found in
the mounted MOSAIC jobs root via filesystem markers. This removes the per-job torch+model reload
that makes a 2 s SLA impossible with the default per-job container. The MOSAIC runtime is UNCHANGED:
it still launches a per-job `object_detection_yolo` container (a thin client, no torch) that signals
this server and collects the result. IPC is purely via the shared host filesystem (this server mounts
the jobs ROOT; the thin client mounts its own step dir — both are bind mounts of the same host paths).

Start out-of-band, one per node that hosts the YOLO step (prewarm every candidate node):
    docker run -d --name yolo-server -v <runtime_dir>/jobs:/data \
        mosaic-object-detection-yolo-server:latest

Protocol, per step dir under the jobs root:
    thin client writes  _yolo.req        (marker; input.json already present = the tiles)
    this server writes  _yolo.out.json   (detection result) then _yolo.done ("ok" | "ERR")
Serial (one job at a time) = this node's YOLO capacity.
"""

import glob
import json
import os
import time
from pathlib import Path

from lib.worker_core import detect_objects, _load_models

JOBS_ROOT = Path(os.environ.get("MOSAIC_JOBS_ROOT", "/data"))
POLL = float(os.environ.get("YOLO_SERVER_POLL", "0.05"))


def _process(step_dir: Path) -> None:
    inp = step_dir / "input.json"
    out = step_dir / "_yolo.out.json"
    done = step_dir / "_yolo.done"
    err = step_dir / "_yolo.err"
    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
        result = detect_objects(data)
        tmp = step_dir / "_yolo.out.json.tmp"
        tmp.write_text(json.dumps(result), encoding="utf-8")
        os.replace(tmp, out)          # atomic publish of the result
        done.write_text("ok", encoding="utf-8")
    except Exception as exc:          # never die on a bad job; report it
        try:
            err.write_text(repr(exc), encoding="utf-8")
        except Exception:
            pass
        try:
            done.write_text("ERR", encoding="utf-8")
        except Exception:
            pass


def main() -> None:
    print("[yolo-server] loading YOLOv8s (one-time warm-up)...", flush=True)
    _load_models()
    print(f"[yolo-server] model warm; watching {JOBS_ROOT} (poll {POLL}s)", flush=True)
    while True:
        for req in glob.glob(str(JOBS_ROOT / "**" / "_yolo.req"), recursive=True):
            step_dir = Path(req).parent
            if (step_dir / "_yolo.done").exists():
                continue              # already served this attempt
            if not (step_dir / "input.json").exists():
                continue
            _process(step_dir)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
