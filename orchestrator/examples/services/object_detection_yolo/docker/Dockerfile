# object_detection_yolo — THIN CLIENT (video pipeline)
#
# Build:  docker build -t mosaic-object-detection-yolo:latest .
#
# This is the per-job container the MOSAIC runtime launches (`docker run --rm`). It does NOT run YOLO
# (no torch, no model) — it delegates to the persistent `mosaic-object-detection-yolo-server` on this
# node via shared-filesystem markers. Hence it is tiny and starts in ~0.1-0.3 s (stdlib only), which is
# what makes a ~2 s end-to-end SLA reachable. The heavy image is the SERVER
# (services/object_detection_yolo_server/), started out-of-band.

FROM python:3.12-slim

WORKDIR /service

COPY main.py /service/main.py

CMD ["python3", "main.py"]
