"""object_detection_yolo — THIN CLIENT (MOSAIC per-job container; video pipeline).

The MOSAIC runtime launches this per job via `docker run --rm` exactly as before — but this container
does NOT run YOLO itself (no torch). It delegates to the persistent `mosaic-object-detection-yolo-server`
container running on this node (which loaded the model once = "prewarm"), so the ~5 s per-job model
reload is eliminated and a ~2 s SLA becomes reachable.

IPC = the shared host filesystem: this container mounts the job's step dir at /data; the server mounts
the jobs ROOT — both are bind mounts of the SAME host paths, so the marker files below are the same files.

Protocol (all in this step dir):
    this client writes  _yolo.req        (marker; input.json = the tiles is already here)
    the server writes   _yolo.out.json   (detection result) then _yolo.done ("ok" | "ERR")
    this client copies   _yolo.out.json  ->  output.json  (what the runtime forwards downstream)
If no server is running on this node, the client times out with a clear error (visible in the run).
"""

import json
import os
import sys
import time
from pathlib import Path

INP = Path(os.environ.get("MOSAIC_INPUT_FILE")
           or os.environ.get("C2TC_INPUT_FILE", "/data/input.json"))
OUT = Path(os.environ.get("MOSAIC_OUTPUT_FILE")
           or os.environ.get("C2TC_OUTPUT_FILE", "/data/output.json"))
D = INP.parent
TIMEOUT = float(os.environ.get("YOLO_CLIENT_TIMEOUT", "110"))  # < runtime step_timeout (120 s)
POLL = 0.05

req = D / "_yolo.req"
done = D / "_yolo.done"
out = D / "_yolo.out.json"
err = D / "_yolo.err"

# Clear any stale markers from a previous attempt so this invocation re-triggers the server.
for p in (done, out, err):
    try:
        p.unlink()
    except FileNotFoundError:
        pass

req.write_text("1", encoding="utf-8")

t0 = time.time()
while time.time() - t0 < TIMEOUT:
    if done.exists():
        break
    time.sleep(POLL)
else:
    sys.exit(f"[yolo-client] timed out after {TIMEOUT}s waiting for the persistent yolo-server "
             f"(is 'mosaic-object-detection-yolo-server' running on this node, mounting the jobs root?)")

status = done.read_text(encoding="utf-8").strip()
if status == "ERR":
    detail = err.read_text(encoding="utf-8") if err.exists() else "(no detail)"
    sys.exit(f"[yolo-client] server reported error: {detail}")

result = json.loads(out.read_text(encoding="utf-8"))
OUT.write_text(json.dumps(result), encoding="utf-8")
