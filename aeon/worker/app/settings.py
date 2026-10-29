import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class WorkerSettings:
    worker_id: str = field(default_factory=lambda: os.getenv("WORKER_ID", "worker-1"))
    port: int = int(os.getenv("WORKER_PORT", "8001"))
    hmac_secret: str = field(default_factory=lambda: os.getenv("HMAC_SHARED_SECRET", "dev-hmac-secret-change-me"))
    max_image_pixels: int = int(os.getenv("MAX_IMAGE_PIXELS", "4000000"))
    max_matrix_n: int = int(os.getenv("MAX_MATRIX_N", "220"))
    nonce_ttl_seconds: int = int(os.getenv("NONCE_TTL_SECONDS", "300"))
    clock_skew_seconds: int = int(os.getenv("CLOCK_SKEW_SECONDS", "300"))


settings = WorkerSettings()
