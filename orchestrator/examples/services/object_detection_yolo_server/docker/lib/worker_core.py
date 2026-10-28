"""Core logic for object_detection_service_yolo: YOLOv8s object detection.

Detection pipeline
------------------
1. Load the YOLOv8s model once and keep it in memory.
2. Decode all tiles from base-64 in parallel (thread pool).
3. Split decoded tiles into groups and run batched inference
   concurrently — each thread uses its own model instance for
   thread-safe parallel execution (per ultralytics recommendation).
4. Collect raw detections per tile (bounding boxes, confidences, classes).
5. Return structured results for the post-processing service.

All processing is fully offline — the model weights are bundled in the
Docker image at build time.  No network calls are made at runtime.

All parameters are fixed to ensure deterministic, stable behaviour.

Usage::

    python worker_core.py
"""

import base64
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Fixed parameters — deterministic, stable behaviour
# ---------------------------------------------------------------------------
_MODEL_PATH = os.environ.get("YOLO_MODEL_PATH", "/model/yolov8s.pt")
_CONFIDENCE_THRESHOLD = 0.25
_IOU_THRESHOLD = 0.45
_MAX_DETECTIONS_PER_TILE = 100
_BATCH_SIZE = 4

# Threading: partition cores between concurrent inference workers
_n_cpus = os.cpu_count() or 4
_NUM_DECODE_WORKERS = max(2, _n_cpus)
_NUM_INFERENCE_WORKERS = max(2, min(4, _n_cpus // 2))

# ---------------------------------------------------------------------------
# Persistent models (loaded once at first invocation)
# ---------------------------------------------------------------------------
_models: list = []


def _load_models():
    """Load per-worker YOLOv8s model instances for thread-safe inference.

    Ultralytics recommends one model instance per thread to avoid
    internal predictor state conflicts.  Each worker gets its own copy.

    Configures PyTorch threading so that each concurrent inference
    worker gets a fair share of CPU cores.
    """
    global _models
    if not _models:
        import torch  # noqa: PLC0415
        from ultralytics import YOLO  # noqa: PLC0415

        torch.set_num_threads(max(1, _n_cpus // _NUM_INFERENCE_WORKERS))

        _models = [YOLO(_MODEL_PATH) for _ in range(_NUM_INFERENCE_WORKERS)]
    return _models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decode_tile(tile_b64: str) -> Image.Image:
    """Decode a base-64 JPEG tile into a PIL RGB Image."""
    raw = base64.b64decode(tile_b64)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _run_batch_inference(
    model,
    images: list[Image.Image],
) -> list[list[dict]]:
    """Run YOLO inference on a batch of PIL Images.

    Returns one list of detection dicts per image.
    """
    results = model(
        images,
        conf=_CONFIDENCE_THRESHOLD,
        iou=_IOU_THRESHOLD,
        max_det=_MAX_DETECTIONS_PER_TILE,
        verbose=False,
    )

    all_detections: list[list[dict]] = []
    for res in results:
        dets: list[dict] = []
        boxes = res.boxes
        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            for i in range(len(boxes)):
                dets.append(
                    {
                        "x1": round(float(xyxy[i][0]), 2),
                        "y1": round(float(xyxy[i][1]), 2),
                        "x2": round(float(xyxy[i][2]), 2),
                        "y2": round(float(xyxy[i][3]), 2),
                        "confidence": round(float(confs[i]), 4),
                        "class_id": int(cls_ids[i]),
                        "class_name": res.names.get(int(cls_ids[i]),
                                                    str(cls_ids[i])),
                    }
                )
        all_detections.append(dets)
    return all_detections



def _infer_chunk(model, chunk: list[Image.Image]) -> list[list[dict]]:
    """Run batched inference on a chunk of images using a dedicated model.

    Each chunk is processed in batches of ``_BATCH_SIZE``.  This
    function is the unit of concurrent work — multiple chunks run
    in parallel threads, each with its own model instance.
    """
    results: list[list[dict]] = []
    for i in range(0, len(chunk), _BATCH_SIZE):
        batch = chunk[i : i + _BATCH_SIZE]
        results.extend(_run_batch_inference(model, batch))
    return results


# ---------------------------------------------------------------------------
# Core service function
# ---------------------------------------------------------------------------

def detect_objects(payload: dict) -> dict:
    """Run YOLOv8s detection on all tiles in *payload*.

    Parameters
    ----------
    payload:
        Must contain ``tiles`` (list of tile dicts from the
        preprocessing service, each with ``tile_b64``).
        All other keys are forwarded unchanged.

    Returns
    -------
    dict
        All original keys (tiles stripped of ``tile_b64``) plus:
        ``detections_per_tile``, ``model_name``,
        ``num_tiles_processed``, ``inference_time_ms``,
        ``total_detections``.
    """
    t0 = time.monotonic()
    result: dict[str, Any] = dict(payload)

    tiles = payload.get("tiles", [])
    models = _load_models()

    # Phase 1: Parallel tile decoding
    tile_b64_list = [t["tile_b64"] for t in tiles]
    with ThreadPoolExecutor(max_workers=_NUM_DECODE_WORKERS) as pool:
        images = list(pool.map(_decode_tile, tile_b64_list))

    # Phase 2: Concurrent batch inference — split tiles into groups and
    # process each group in a separate thread with its own model instance.
    # Per ultralytics recommendation, each thread has a dedicated YOLO
    # instance to avoid internal predictor state conflicts.
    t_infer = time.monotonic()

    n_groups = min(len(models), max(1, len(images)))
    chunk_size = max(1, (len(images) + n_groups - 1) // n_groups)
    chunks = [
        images[i : i + chunk_size]
        for i in range(0, len(images), chunk_size)
    ]

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futures = [
            pool.submit(_infer_chunk, models[i], chunk)
            for i, chunk in enumerate(chunks)
        ]
        chunk_results = [f.result() for f in futures]

    inference_ms = round((time.monotonic() - t_infer) * 1000, 2)

    # Flatten results (order preserved)
    all_detections: list[list[dict]] = []
    for cr in chunk_results:
        all_detections.extend(cr)

    # Build structured output
    total_dets = 0
    detections_per_tile: list[dict] = []
    for i, tile in enumerate(tiles):
        dets = all_detections[i] if i < len(all_detections) else []
        total_dets += len(dets)
        detections_per_tile.append(
            {
                "tile_id": tile["tile_id"],
                "x_offset": tile.get("x_offset", 0),
                "y_offset": tile.get("y_offset", 0),
                "tile_width": tile.get("tile_width", 0),
                "tile_height": tile.get("tile_height", 0),
                "scale": tile.get("scale", 1.0),
                "detections": dets,
            }
        )

    elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

    result["detections_per_tile"] = detections_per_tile
    result["model_name"] = "yolov8s"
    result["num_tiles_processed"] = len(tiles)
    result["inference_time_ms"] = inference_ms
    result["total_detections"] = total_dets

    # Strip tile pixel data — downstream only needs spatial metadata
    if "tiles" in result:
        for tile in result["tiles"]:
            tile.pop("tile_b64", None)

    return result


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    # Create a minimal 640×640 test tile
    test_img = Image.new("RGB", (640, 640), color=(100, 150, 200))
    buf = io.BytesIO()
    test_img.save(buf, format="JPEG")
    tile_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    sample = {
        "filename": "test.jpg",
        "original_width": 640,
        "original_height": 640,
        "tiles": [
            {
                "tile_id": 0,
                "x_offset": 0,
                "y_offset": 0,
                "tile_width": 640,
                "tile_height": 640,
                "scale": 1.0,
                "quality": {"blur_score": 0, "contrast": 0, "brightness": 150},
                "tile_b64": tile_b64,
            }
        ],
        "num_tiles": 1,
        "target_tile_size": 640,
    }

    out = detect_objects(sample)
    for t in out.get("tiles", []):
        t.pop("tile_b64", None)
    print(json.dumps(out, indent=2))
