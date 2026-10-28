"""TG-VIDEO: images at a CONSTANT per-job intensity (video pipeline).
The LOAD LEVER is the image RESOLUTION (bigger image -> more tiles -> more YOLO inferences
-> higher per-job CPU).
Returned keys: ``image_b64``, ``filename``, ``image_format``, ``profile``, ``tick``.
"""

import base64
import os
import struct
from pathlib import Path

_TG_DIR = Path(__file__).resolve().parent
_IMAGE_DIR = Path(os.environ.get("MOSAIC_IMAGE_DIR")
                  or os.environ.get("C2TC_IMAGE_DIR", str(_TG_DIR / "images")))
_SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
_FMT = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png",
        ".bmp": "bmp", ".tiff": "tiff", ".webp": "webp"}

_tick = 0
_files: list[Path] | None = None
_b64_cache: dict[str, str] = {}


def _discover() -> list[Path]:
    """Sorted (deterministic) list of bundled images; tiny synthetic fallback for smoke-tests."""
    if _IMAGE_DIR.exists():
        files = sorted(
            p for p in _IMAGE_DIR.rglob("*")
            if p.is_file() and p.suffix.lower() in _SUPPORTED
        )
        if files:
            return files
    return _make_synthetic()


def _make_synthetic(count: int = 8, width: int = 640, height: int = 480) -> list[Path]:
    """Deterministic BMP test images (pure stdlib) so the pipeline is runnable without real data.

    Not meant for real measurements: bundle real images under images/ (see images/README.txt).
    Deterministic (seeded by index), so still reproducible.
    """
    out = _IMAGE_DIR
    out.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for idx in range(count):
        pixels = bytearray(width * height * 3)
        bg = (40 + idx * 3) % 200
        for i in range(0, len(pixels), 3):
            pixels[i] = bg
            pixels[i + 1] = (bg + 40) % 256
            pixels[i + 2] = (bg + 80) % 256
        # a few deterministic rectangles
        for r in range(3 + idx % 4):
            rx = (37 * (r + 1) + 11 * idx) % (width - 60)
            ry = (29 * (r + 1) + 7 * idx) % (height - 60)
            rw, rh = 40 + (r * 13) % 120, 40 + (r * 17) % 100
            cr, cg, cb = (80 + 30 * r) % 256, (120 + 20 * r) % 256, (160 + 10 * r) % 256
            for y in range(ry, min(ry + rh, height)):
                base = y * width * 3
                for x in range(rx, min(rx + rw, width)):
                    off = base + x * 3
                    pixels[off], pixels[off + 1], pixels[off + 2] = cb, cg, cr
        row_size = (width * 3 + 3) & ~3
        pdata = row_size * height
        bmp = bytearray(54)
        bmp[0:2] = b"BM"
        struct.pack_into("<I", bmp, 2, 54 + pdata)
        struct.pack_into("<I", bmp, 10, 54)
        struct.pack_into("<I", bmp, 14, 40)
        struct.pack_into("<i", bmp, 18, width)
        struct.pack_into("<i", bmp, 22, height)
        struct.pack_into("<H", bmp, 26, 1)
        struct.pack_into("<H", bmp, 28, 24)
        rows = bytearray(pdata)
        for y in range(height):
            src = (height - 1 - y) * width * 3
            dst = y * row_size
            rows[dst:dst + width * 3] = pixels[src:src + width * 3]
        path = out / f"synthetic_{idx:03d}.bmp"
        path.write_bytes(bytes(bmp) + bytes(rows))
        made.append(path)
    return sorted(made)


def traffic_generator() -> dict:
    global _tick, _files
    _tick += 1
    if _files is None:
        _files = _discover()
    img = _files[(_tick - 1) % len(_files)]
    key = str(img)
    if key not in _b64_cache:
        _b64_cache[key] = base64.b64encode(img.read_bytes()).decode("ascii")
    return {
        "image_b64": _b64_cache[key],
        "filename": img.name,
        "image_format": _FMT.get(img.suffix.lower(), "jpeg"),
        "profile": "video",
        "tick": _tick,
    }


if __name__ == "__main__":
    import json
    rec = traffic_generator()
    prev = dict(rec)
    prev["image_b64"] = prev["image_b64"][:60] + "..."
    print(json.dumps(prev, indent=2))
