# detection_postprocessing_service — Cross-tile NMS & aggregation
#
# Build:
#   docker build -t detection_postprocessing_service:latest .
#
# All parameters are fixed — no runtime configuration needed.
# Always uses Soft-NMS for refined suppression.

FROM python:3.12-slim

WORKDIR /service

COPY requirements.txt /service/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py /service/main.py
COPY lib/    /service/lib/

CMD ["python3", "main.py"]
