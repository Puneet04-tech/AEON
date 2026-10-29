"""Real compute jobs. No stubs: these actually allocate, compute and hash.

  image_resize     – synthesise a deterministic image, resize it, hash the pixels
  matrix_multiply  – deterministic integer matrix product with numpy
"""
import hashlib
import io
import json
from typing import Any, Dict

import numpy as np
from PIL import Image

from app.settings import settings


class JobError(Exception):
    def __init__(self, message: str, code: str = "job_failed"):
        super().__init__(message)
        self.code = code


def canonical_digest(result: Dict[str, Any]) -> str:
    blob = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _synth_image(width: int, height: int, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    # Smooth gradient plus noise so resizing has real work and real entropy.
    xs = np.linspace(0, 255, width, dtype=np.float32)
    ys = np.linspace(0, 255, height, dtype=np.float32)
    base = (xs[None, :] + ys[:, None]) % 255.0
    noise = rng.normal(0, 12, size=(height, width)).astype(np.float32)
    channel = np.clip(base + noise, 0, 255).astype(np.uint8)
    rgb = np.stack([channel, np.flipud(channel), np.roll(channel, 7, axis=1)], axis=-1)
    return Image.fromarray(rgb, mode="RGB")


def run_image_resize(params: Dict[str, Any]) -> Dict[str, Any]:
    source_w = int(params.get("source_width", 1280))
    source_h = int(params.get("source_height", 960))
    out_w = int(params.get("width", 320))
    out_h = int(params.get("height", 240))
    seed = int(params.get("seed", 7))

    if source_w * source_h > settings.max_image_pixels:
        raise JobError("image exceeds the pixel limit", "size_limit")
    if not (1 <= out_w <= 4096 and 1 <= out_h <= 4096):
        raise JobError("output dimensions out of range", "size_limit")

    image = _synth_image(source_w, source_h, seed)
    resized = image.resize((out_w, out_h), Image.LANCZOS)
    buffer = io.BytesIO()
    resized.save(buffer, format="PNG", optimize=False)
    payload = buffer.getvalue()
    pixels = np.asarray(resized)
    return {
        "kind": "image_resize",
        "source": {"width": source_w, "height": source_h, "pixels": source_w * source_h},
        "output": {"width": out_w, "height": out_h, "format": "PNG", "bytes": len(payload)},
        "pixel_digest": hashlib.sha256(pixels.tobytes()).hexdigest(),
        "mean_rgb": [round(float(v), 2) for v in pixels.reshape(-1, 3).mean(axis=0)],
    }


def run_matrix_multiply(params: Dict[str, Any]) -> Dict[str, Any]:
    n = int(params.get("n", 96))
    seed = int(params.get("seed", 11))
    if not (2 <= n <= settings.max_matrix_n):
        raise JobError("matrix size out of range", "size_limit")

    rng = np.random.default_rng(seed)
    a = rng.integers(-50, 50, size=(n, n), dtype=np.int64)
    b = rng.integers(-50, 50, size=(n, n), dtype=np.int64)
    product = a @ b
    return {
        "kind": "matrix_multiply",
        "n": n,
        "trace": int(np.trace(product)),
        "frobenius": int(np.sqrt((product.astype(np.float64) ** 2).sum())),
        "result_digest": hashlib.sha256(product.tobytes()).hexdigest(),
        "sample": product[:2, :2].tolist(),
    }


HANDLERS = {
    "image_resize": run_image_resize,
    "matrix_multiply": run_matrix_multiply,
}


def run_job(job_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    handler = HANDLERS.get(job_type)
    if handler is None:
        raise JobError(f"unknown job type {job_type}", "unknown_job")
    return handler(params)
