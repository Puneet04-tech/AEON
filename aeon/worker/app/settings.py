import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# The worker is a separate process from the API but must sign jobs with the same
# HMAC secret. Load the shared env so a plain `uvicorn app.main:app` picks up the
# project's .env instead of silently falling back to the dev secret.
for candidate in (Path(".env"), Path("../.env")):
    if candidate.is_file():
        load_dotenv(candidate, override=False)


@dataclass
class WorkerSettings:
    worker_id: str = field(default_factory=lambda: os.getenv("WORKER_ID", "worker-1"))
    port: int = int(os.getenv("WORKER_PORT") or os.getenv("PORT") or "8001")
    hmac_secret: str = field(default_factory=lambda: os.getenv("HMAC_SHARED_SECRET", "dev-hmac-secret-change-me"))
    max_image_pixels: int = int(os.getenv("MAX_IMAGE_PIXELS", "4000000"))
    max_matrix_n: int = int(os.getenv("MAX_MATRIX_N", "220"))
    nonce_ttl_seconds: int = int(os.getenv("NONCE_TTL_SECONDS", "300"))
    clock_skew_seconds: int = int(os.getenv("CLOCK_SKEW_SECONDS", "300"))


settings = WorkerSettings()
