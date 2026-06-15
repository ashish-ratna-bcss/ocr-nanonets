"""Runtime configuration, all from environment variables.

Defaults are chosen so the stack runs with only API_KEY set. The Docker
images mount /data and the HF cache as volumes, so the defaults below match
the container paths.
"""

import os
from pathlib import Path


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Settings:
    # Shared secret the Next app must send as: Authorization: Bearer <key>.
    # Required - the service refuses to start without it (see check()).
    API_KEY: str = os.environ.get("API_KEY", "")

    # Where jobs (input PDF, per-page checkpoints, output.md) live.
    DATA_DIR: Path = Path(os.environ.get("DATA_DIR", "/data"))
    DB_PATH: Path = Path(os.environ.get("DB_PATH", "/data/jobs.db"))

    # Auto-delete finished/failed jobs older than this many days (sensitive
    # data - do not hoard). 0 disables cleanup.
    RETENTION_DAYS: int = _int("RETENTION_DAYS", 7)

    # OCR knobs.
    MODEL_ID: str = os.environ.get("MODEL_ID", "nanonets/Nanonets-OCR2-3B")
    RENDER_DPI: int = _int("RENDER_DPI", 300)

    # Reject absurd uploads early. Also enforced by nginx body size.
    MAX_PAGES: int = _int("MAX_PAGES", 300)
    MAX_UPLOAD_MB: int = _int("MAX_UPLOAD_MB", 300)

    # Worker poll interval (seconds) when the queue is empty.
    POLL_SECONDS: int = _int("POLL_SECONDS", 2)

    def check(self):
        if not self.API_KEY:
            raise RuntimeError(
                "API_KEY env var is required. Set it in .env "
                "(see .env.example)."
            )
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
