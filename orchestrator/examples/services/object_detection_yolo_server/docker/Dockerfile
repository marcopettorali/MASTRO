# mosaic-object-detection-yolo-server — PERSISTENT YOLOv8s model server (video pipeline)
#
# Build:  docker build -t mosaic-object-detection-yolo-server:latest .
# Run  :  docker run -d --name yolo-server -v <runtime_dir>/jobs:/data mosaic-object-detection-yolo-server:latest
#
# Loads the model ONCE and serves per-job requests via filesystem markers (see server.py).
# CPU-only torch (MOSAIC runs YOLO on CPU; containers get no --gpus). Weights baked in at build time.

FROM python:3.12-slim

WORKDIR /service

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcb1 \
    libgl1 \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /service/requirements.txt
# CPU-only torch first (much smaller than the default CUDA build; identical YOLOv8s results),
# so ultralytics reuses it instead of pulling the multi-GB CUDA torch + nvidia-* libraries.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py /service/server.py
COPY lib/       /service/lib/

# Download YOLOv8s weights at build time so the container is self-contained (offline at runtime).
RUN python3 -c "\
from ultralytics import YOLO; \
m = YOLO('yolov8s.pt'); \
print('YOLOv8s loaded:', m.model_name if hasattr(m, 'model_name') else 'ok')" \
    && mkdir -p /model \
    && find /root -name 'yolov8s.pt' -exec cp {} /model/yolov8s.pt \;

ENV YOLO_MODEL_PATH=/model/yolov8s.pt

CMD ["python3", "server.py"]
