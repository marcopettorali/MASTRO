"""Core logic for image_preprocessing_service: multi-scale tile preparation.

Converts an incoming base-64 encoded image into a set of overlapping
tiles ready for object detection inference.

Preprocessing pipeline
----------------------
1. Decode the base-64 image payload.
2. Apply per-channel histogram equalisation to improve contrast.
3. Apply unsharp-mask sharpening to enhance edges.
4. Generate multi-scale overlapping tiles (always 3 scales).
5. Resize each tile to 640×640 (target model input size).
6. Compute per-tile quality metrics (blur score, contrast, brightness).
7. Encode each tile as JPEG base-64 for transmission.

Tile processing (crop, resize, quality computation, JPEG encoding) is
parallelised across CPU cores using a thread pool.  PIL and numpy
operations release the GIL, enabling true multicore execution.

All parameters are fixed to ensure deterministic, stable behaviour.
All processing is fully offline — no network calls are made.

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
from PIL import Image, ImageFilter

# ---------------------------------------------------------------------------
# Fixed parameters — deterministic, stable behaviour
# ---------------------------------------------------------------------------
_TARGET_SIZE = 640
_TILE_OVERLAP = 0.25
_SCALES = [0.5, 1.0, 1.5]  # always 3 scales
_JPEG_QUALITY = 90
_MIN_TILE_DIMENSION = 64
_NUM_WORKERS = max(2, os.cpu_count() or 2)


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _decode_image(image_b64: str) -> Image.Image:
    """Decode a base-64 string into a PIL RGB Image."""
    raw = base64.b64decode(image_b64)
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _histogram_equalize(img: Image.Image) -> Image.Image:
    """Per-channel histogram equalisation.

    Spreads intensity values across the full 0–255 range per channel,
    improving contrast for better object detection.
    """
    arr = np.array(img, dtype=np.float32)
    for c in range(3):
        channel = arr[:, :, c]
        hist, _ = np.histogram(channel.ravel(), bins=256, range=(0, 255))
        cdf = hist.cumsum()
        cdf_min = cdf[cdf > 0].min() if np.any(cdf > 0) else 0
        total = channel.size
        if total > cdf_min:
            cdf_norm = (cdf - cdf_min) / (total - cdf_min) * 255.0
            arr[:, :, c] = cdf_norm[channel.astype(np.int32).clip(0, 255)]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def _sharpen_image(img: Image.Image) -> Image.Image:
    """Apply unsharp-mask sharpening to enhance edges for detection."""
    return img.filter(
        ImageFilter.UnsharpMask(radius=2.0, percent=50, threshold=1)
    )


def _compute_tile_quality(tile_arr: np.ndarray) -> dict:
    """Compute quality metrics for a single tile.

    Returns blur score (Laplacian variance), contrast (std-dev of
    intensity), and mean brightness.
    """
    gray = np.mean(tile_arr.astype(np.float32), axis=2)

    # Laplacian variance — high value ⇒ sharp; low ⇒ blurry
    lap = (
        np.roll(gray, 1, axis=0)
        + np.roll(gray, -1, axis=0)
        + np.roll(gray, 1, axis=1)
        + np.roll(gray, -1, axis=1)
        - 4 * gray
    )
    blur_score = float(np.var(lap))
    contrast = float(np.std(gray))
    brightness = float(np.mean(gray))

    return {
        "blur_score": round(blur_score, 2),
        "contrast": round(contrast, 2),
        "brightness": round(brightness, 2),
    }


# ---------------------------------------------------------------------------
# Core service function
# ---------------------------------------------------------------------------

def preprocess_image(payload: dict) -> dict:
    """Preprocess an image for the object-detection pipeline.

    Parameters
    ----------
    payload:
        Must contain ``image_b64`` (base-64 encoded image).
        All other keys are forwarded unchanged.

    Returns
    -------
    dict
        All original keys (minus ``image_b64``) plus:
        ``original_width``, ``original_height``, ``tiles`` (list),
        ``num_tiles``, ``target_tile_size``, ``scales_used``,
        ``tiles_per_scale``, ``preprocessing_ms``.
    """
    t0 = time.monotonic()
    result: dict[str, Any] = dict(payload)

    image_b64: str = payload.get("image_b64", "")

    # 1. Decode image
    img = _decode_image(image_b64)
    orig_w, orig_h = img.size

    # 2. Per-channel histogram equalisation
    img = _histogram_equalize(img)

    # 3. Edge-aware sharpening
    img = _sharpen_image(img)

    # Force full pixel loading for thread-safe concurrent access
    img.load()

    # 4. Pre-scale images for all scales (parallel — each resize is
    #    a CPU-intensive LANCZOS resampling that releases the GIL)
    def _make_scaled(scale: float) -> tuple[float, Image.Image]:
        if abs(scale - 1.0) < 1e-9:
            s = img.copy()
        else:
            new_w = max(_MIN_TILE_DIMENSION, int(orig_w * scale))
            new_h = max(_MIN_TILE_DIMENSION, int(orig_h * scale))
            s = img.resize((new_w, new_h), Image.LANCZOS)
        s.load()
        return scale, s

    scaled_images: dict[float, Image.Image] = {}
    with ThreadPoolExecutor(max_workers=len(_SCALES)) as pool:
        for scale, scaled in pool.map(_make_scaled, _SCALES):
            scaled_images[scale] = scaled

    # 5. Generate tile specifications for all scales
    stride = max(1, int(_TARGET_SIZE * (1.0 - _TILE_OVERLAP)))
    tile_specs: list[tuple[float, int, int, int, int]] = []
    tiles_per_scale: dict[str, int] = {}

    for scale in _SCALES:
        scaled = scaled_images[scale]
        sw, sh = scaled.size
        scale_count = 0

        y = 0
        while y < sh:
            x = 0
            while x < sw:
                x2 = min(x + _TARGET_SIZE, sw)
                y2 = min(y + _TARGET_SIZE, sh)
                x1 = max(0, x2 - _TARGET_SIZE)
                y1 = max(0, y2 - _TARGET_SIZE)
                tile_specs.append((scale, x1, y1, x2, y2))
                scale_count += 1
                x += stride
                if x2 >= sw:
                    break
            y += stride
            if y2 >= sh:
                break

        tiles_per_scale[str(scale)] = scale_count

    # 6. Process tiles in parallel (crop, resize, quality metrics, encode).
    #    PIL crop/resize and numpy quality computation release the GIL,
    #    enabling true multicore execution.
    def _process_tile(spec: tuple[float, int, int, int, int]) -> dict:
        scale, x1, y1, x2, y2 = spec
        scaled = scaled_images[scale]

        tile_img = scaled.crop((x1, y1, x2, y2))
        if tile_img.size != (_TARGET_SIZE, _TARGET_SIZE):
            tile_img = tile_img.resize(
                (_TARGET_SIZE, _TARGET_SIZE), Image.LANCZOS
            )

        tile_arr = np.array(tile_img)
        quality = _compute_tile_quality(tile_arr)

        buf = io.BytesIO()
        tile_img.save(buf, format="JPEG", quality=_JPEG_QUALITY)
        tile_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        orig_x = int(x1 / scale) if abs(scale) > 1e-9 else x1
        orig_y = int(y1 / scale) if abs(scale) > 1e-9 else y1

        return {
            "x_offset": orig_x,
            "y_offset": orig_y,
            "tile_width": x2 - x1,
            "tile_height": y2 - y1,
            "scale": round(scale, 4),
            "quality": quality,
            "tile_b64": tile_b64,
        }

    with ThreadPoolExecutor(max_workers=_NUM_WORKERS) as pool:
        all_tiles = list(pool.map(_process_tile, tile_specs))

    # Sequential tile IDs
    for idx, tile in enumerate(all_tiles):
        tile["tile_id"] = idx

    elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

    result.update(
        {
            "original_width": orig_w,
            "original_height": orig_h,
            "tiles": all_tiles,
            "num_tiles": len(all_tiles),
            "target_tile_size": _TARGET_SIZE,
            "scales_used": _SCALES,
            "tiles_per_scale": tiles_per_scale,
            "preprocessing_ms": elapsed_ms,
        }
    )

    # Drop raw image — the tiles are the processed output
    result.pop("image_b64", None)

    return result


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json

    # Create a minimal 200×150 RGB test image
    test_img = Image.new("RGB", (200, 150), color=(100, 120, 80))
    buf = io.BytesIO()
    test_img.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    sample = {
        "filename": "test.jpg",
        "image_b64": b64,
        "image_format": "jpeg",
    }

    out = preprocess_image(sample)
    # Trim tile data for display
    for t in out.get("tiles", []):
        t["tile_b64"] = t["tile_b64"][:40] + "..."

    print(json.dumps(out, indent=2))
