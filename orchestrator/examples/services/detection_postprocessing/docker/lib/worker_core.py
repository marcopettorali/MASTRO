"""Core logic for detection_postprocessing_service: cross-tile NMS & aggregation.

Post-processing pipeline
------------------------
1. Remap tile-local detections back to original image coordinates,
   accounting for tile offsets and scale factors (parallel per tile).
2. Apply per-class Soft-NMS across all tiles to merge overlapping
   detections (parallel per class).
3. Filter detections by a final confidence threshold.
4. Compute rich detection statistics (per-class distribution, spatial
   coverage, global ranking).
5. Format and return the clean, final result.

Per-tile remapping and per-class NMS are parallelised across CPU cores
using a thread pool.  Numpy operations release the GIL, enabling true
multicore execution.

All parameters are fixed to ensure deterministic, stable behaviour.
All processing is fully offline — no network calls are made.

Usage::

    python worker_core.py
"""

import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Fixed parameters — deterministic, stable behaviour
# ---------------------------------------------------------------------------
_NMS_IOU_THRESHOLD = 0.45
_FINAL_CONFIDENCE_THRESHOLD = 0.30
_MAX_DETECTIONS = 100
_SOFT_NMS_SIGMA = 0.5
_NUM_WORKERS = max(2, os.cpu_count() or 2)


# ---------------------------------------------------------------------------
# Coordinate remapping (per-tile unit of parallel work)
# ---------------------------------------------------------------------------

def _remap_tile_detections(tile_info: dict) -> list[dict]:
    """Remap detections from a single tile to the original image space.

    Each tile carries ``x_offset``, ``y_offset``, and ``scale`` fields
    that describe where it was cropped from the original image.  We
    reverse these transformations so that all detections are expressed in
    the original image coordinate system.
    """
    x_off = tile_info.get("x_offset", 0)
    y_off = tile_info.get("y_offset", 0)
    scale = tile_info.get("scale", 1.0)

    remapped: list[dict] = []
    for det in tile_info.get("detections", []):
        if abs(scale) > 1e-9:
            orig_x1 = det["x1"] / scale + x_off
            orig_y1 = det["y1"] / scale + y_off
            orig_x2 = det["x2"] / scale + x_off
            orig_y2 = det["y2"] / scale + y_off
        else:
            orig_x1 = det["x1"] + x_off
            orig_y1 = det["y1"] + y_off
            orig_x2 = det["x2"] + x_off
            orig_y2 = det["y2"] + y_off

        remapped.append(
            {
                "x1": round(orig_x1, 2),
                "y1": round(orig_y1, 2),
                "x2": round(orig_x2, 2),
                "y2": round(orig_y2, 2),
                "confidence": det["confidence"],
                "class_id": det["class_id"],
                "class_name": det["class_name"],
                "source_tile_id": tile_info.get("tile_id", -1),
                "source_scale": scale,
            }
        )
    return remapped


# ---------------------------------------------------------------------------
# NMS algorithms
# ---------------------------------------------------------------------------

def _soft_nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float,
    sigma: float = 0.5,
    score_threshold: float = 0.01,
) -> tuple[list[int], np.ndarray]:
    """Soft-NMS: Gaussian decay of overlapping scores.

    Instead of hard suppression, overlapping boxes have their scores
    decayed by a Gaussian function of IoU, preserving partially
    overlapping detections that may correspond to distinct objects.

    Returns (indices_to_keep, updated_scores).
    """
    n = len(scores)
    working_scores = scores.copy()
    indices = list(range(n))
    keep: list[int] = []

    while indices:
        best_local = max(indices, key=lambda i: working_scores[i])
        if working_scores[best_local] < score_threshold:
            break
        keep.append(best_local)
        indices.remove(best_local)

        for j in indices:
            xx1 = max(boxes[best_local, 0], boxes[j, 0])
            yy1 = max(boxes[best_local, 1], boxes[j, 1])
            xx2 = min(boxes[best_local, 2], boxes[j, 2])
            yy2 = min(boxes[best_local, 3], boxes[j, 3])

            inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
            area_a = (
                (boxes[best_local, 2] - boxes[best_local, 0])
                * (boxes[best_local, 3] - boxes[best_local, 1])
            )
            area_b = (
                (boxes[j, 2] - boxes[j, 0])
                * (boxes[j, 3] - boxes[j, 1])
            )
            union = area_a + area_b - inter
            iou = inter / union if union > 0 else 0.0

            if iou > 0:
                decay = math.exp(-(iou * iou) / sigma)
                working_scores[j] *= decay

    return keep, working_scores


def _nms_for_class(cls_dets: list[dict]) -> list[dict]:
    """Run Soft-NMS on detections belonging to a single class.

    This is the unit of parallel work — each class is processed
    independently by a separate thread.
    """
    if not cls_dets:
        return []

    boxes = np.array(
        [[d["x1"], d["y1"], d["x2"], d["y2"]] for d in cls_dets],
        dtype=np.float64,
    )
    scores = np.array(
        [d["confidence"] for d in cls_dets], dtype=np.float64,
    )

    keep_idx, updated_scores = _soft_nms(
        boxes, scores, _NMS_IOU_THRESHOLD, sigma=_SOFT_NMS_SIGMA,
    )

    kept: list[dict] = []
    for idx in keep_idx:
        det = dict(cls_dets[idx])
        det["confidence"] = round(float(updated_scores[idx]), 4)
        kept.append(det)

    return kept


# ---------------------------------------------------------------------------
# Detection statistics
# ---------------------------------------------------------------------------

def _compute_statistics(detections: list[dict], orig_w: int, orig_h: int) -> dict:
    """Compute rich summary statistics for the final detection set.

    Returns per-class distribution with counts and average confidence,
    global average confidence, and spatial coverage fraction.
    """
    if not detections:
        return {
            "num_detections": 0,
            "avg_confidence": 0.0,
            "class_distribution": {},
            "spatial_coverage": 0.0,
        }

    # Per-class distribution
    by_class: dict[str, list[dict]] = {}
    for det in detections:
        name = det["class_name"]
        by_class.setdefault(name, []).append(det)

    class_distribution: dict[str, dict] = {}
    for name, cls_dets in by_class.items():
        confs = [d["confidence"] for d in cls_dets]
        areas = [
            max(0, d["x2"] - d["x1"]) * max(0, d["y2"] - d["y1"])
            for d in cls_dets
        ]
        class_distribution[name] = {
            "count": len(cls_dets),
            "avg_confidence": round(sum(confs) / len(confs), 4),
            "total_area": round(sum(areas), 2),
        }

    # Global average confidence
    avg_conf = sum(d["confidence"] for d in detections) / len(detections)

    # Spatial coverage: fraction of image area covered by detections
    total_det_area = sum(
        max(0, d["x2"] - d["x1"]) * max(0, d["y2"] - d["y1"])
        for d in detections
    )
    image_area = max(1, orig_w * orig_h)
    coverage = min(1.0, total_det_area / image_area)

    return {
        "num_detections": len(detections),
        "avg_confidence": round(avg_conf, 4),
        "class_distribution": class_distribution,
        "spatial_coverage": round(coverage, 4),
    }


# ---------------------------------------------------------------------------
# Core service function
# ---------------------------------------------------------------------------

def postprocess_detections(payload: dict) -> dict:
    """Post-process raw tile detections into a clean final result.

    Parameters
    ----------
    payload:
        Must contain ``detections_per_tile`` (list of per-tile
        detection structures from Service 2).
        All other keys are forwarded unchanged.

    Returns
    -------
    dict
        All original keys (minus ``detections_per_tile`` and ``tiles``)
        plus: ``detections`` (final list), ``statistics``,
        ``postprocessing_ms``.
    """
    t0 = time.monotonic()
    result: dict[str, Any] = dict(payload)

    detections_per_tile = payload.get("detections_per_tile", [])
    orig_w = payload.get("original_width", 1)
    orig_h = payload.get("original_height", 1)

    # 1. Parallel coordinate remapping — each tile processed independently
    with ThreadPoolExecutor(max_workers=_NUM_WORKERS) as pool:
        tile_dets = list(pool.map(_remap_tile_detections, detections_per_tile))

    all_dets: list[dict] = []
    for td in tile_dets:
        all_dets.extend(td)

    # 2. Clip to image bounds
    for det in all_dets:
        det["x1"] = round(max(0, min(det["x1"], orig_w)), 2)
        det["y1"] = round(max(0, min(det["y1"], orig_h)), 2)
        det["x2"] = round(max(0, min(det["x2"], orig_w)), 2)
        det["y2"] = round(max(0, min(det["y2"], orig_h)), 2)

    # 3. Per-class Soft-NMS in parallel — each class processed
    #    independently by a separate thread
    by_class: dict[int, list[dict]] = {}
    for det in all_dets:
        by_class.setdefault(det["class_id"], []).append(det)

    with ThreadPoolExecutor(max_workers=_NUM_WORKERS) as pool:
        class_results = list(pool.map(_nms_for_class, by_class.values()))

    merged: list[dict] = []
    for cr in class_results:
        merged.extend(cr)

    # 4. Global ranking by confidence
    merged.sort(key=lambda d: d["confidence"], reverse=True)

    # 5. Final confidence filter + limit
    final = [
        d for d in merged
        if d["confidence"] >= _FINAL_CONFIDENCE_THRESHOLD
    ][: _MAX_DETECTIONS]

    # 6. Clean up auxiliary fields
    for det in final:
        det.pop("source_tile_id", None)
        det.pop("source_scale", None)

    # 7. Compute rich statistics
    stats = _compute_statistics(final, orig_w, orig_h)

    elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

    result["detections"] = final
    result["statistics"] = stats
    result["postprocessing_ms"] = elapsed_ms

    # Remove intermediate data — only final result propagates
    result.pop("detections_per_tile", None)
    result.pop("tiles", None)

    return result


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    sample = {
        "filename": "test.jpg",
        "original_width": 1920,
        "original_height": 1080,
        "model_name": "yolov8s",
        "detections_per_tile": [
            {
                "tile_id": 0,
                "x_offset": 0,
                "y_offset": 0,
                "tile_width": 640,
                "tile_height": 640,
                "scale": 1.0,
                "detections": [
                    {
                        "x1": 50, "y1": 80, "x2": 200, "y2": 300,
                        "confidence": 0.92, "class_id": 1,
                        "class_name": "person",
                    },
                    {
                        "x1": 300, "y1": 100, "x2": 500, "y2": 400,
                        "confidence": 0.85, "class_id": 3,
                        "class_name": "car",
                    },
                ],
            },
            {
                "tile_id": 1,
                "x_offset": 480,
                "y_offset": 0,
                "tile_width": 640,
                "tile_height": 640,
                "scale": 1.0,
                "detections": [
                    {
                        "x1": 10, "y1": 100, "x2": 180, "y2": 400,
                        "confidence": 0.88, "class_id": 3,
                        "class_name": "car",
                    },
                ],
            },
        ],
    }

    out = postprocess_detections(sample)
    print(json.dumps(out, indent=2))
