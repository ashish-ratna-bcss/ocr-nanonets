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

    # CORS. "*" = allow any origin (dev / server-to-server). For production
    # browser clients, set a comma-separated allowlist, e.g.
    #   CORS_ORIGINS=https://app.example.com,https://admin.example.com
    # Spec forbids credentials with "*", so credentials are forced off in
    # that case (see cors_config()). Our auth is a Bearer header, not a
    # cookie, so credentials are not needed for the common case anyway.
    CORS_ORIGINS: str = os.environ.get("CORS_ORIGINS", "*")
    CORS_ALLOW_CREDENTIALS: bool = (
        os.environ.get("CORS_ALLOW_CREDENTIALS", "false").lower()
        in ("1", "true", "yes")
    )

    # Where jobs (input PDF, per-page checkpoints, output.md) live.
    DATA_DIR: Path = Path(os.environ.get("DATA_DIR", "/data"))
    DB_PATH: Path = Path(os.environ.get("DB_PATH", "/data/jobs.db"))

    # Auto-delete finished/failed jobs older than this many days (sensitive
    # data - do not hoard). 0 disables cleanup.
    RETENTION_DAYS: int = _int("RETENTION_DAYS", 7)

    # OCR knobs.
    MODEL_ID: str = os.environ.get("MODEL_ID", "nanonets/Nanonets-OCR2-3B")
    RENDER_DPI: int = _int("RENDER_DPI", 300)
    MIN_PIXELS: int = _int("MIN_PIXELS", 256 * 28 * 28)
    MAX_PIXELS: int = _int("MAX_PIXELS", 768 * 28 * 28)

    # Reject absurd uploads early. Also enforced by nginx body size.
    MAX_PAGES: int = _int("MAX_PAGES", 300)
    MAX_UPLOAD_MB: int = _int("MAX_UPLOAD_MB", 300)

    # Worker poll interval (seconds) when the queue is empty.
    POLL_SECONDS: int = _int("POLL_SECONDS", 2)

    def cors_config(self):
        """Resolve CORS settings into kwargs for CORSMiddleware.

        Returns (allow_origins, allow_credentials). Wildcard origins force
        credentials off because the CORS spec disallows the combination and
        browsers reject it.
        """
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        if not origins or "*" in origins:
            return ["*"], False
        return origins, self.CORS_ALLOW_CREDENTIALS

    def check(self):
        if not self.API_KEY:
            raise RuntimeError(
                "API_KEY env var is required. Set it in .env "
                "(see .env.example)."
            )
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
