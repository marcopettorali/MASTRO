# image_preprocessing_service — Multi-scale tile preparation
#
# Build:
#   docker build -t image_preprocessing_service:latest .
#
# All parameters are fixed — no runtime configuration needed.

FROM python:3.12-slim

WORKDIR /service

COPY requirements.txt /service/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py /service/main.py
COPY lib/    /service/lib/

CMD ["python3", "main.py"]
