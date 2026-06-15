"""SQLite-backed job store. Shared by the API (writes new jobs, reads
status) and the worker (claims and updates jobs). SQLite with WAL handles
this two-process access fine for our low request rate.

Status lifecycle: queued -> processing -> done | failed
"""

import sqlite3
import time
import uuid
from contextlib import contextmanager

from .settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    filename      TEXT,
    status        TEXT NOT NULL DEFAULT 'queued',
    total_pages   INTEGER DEFAULT 0,
    pages_done    INTEGER DEFAULT 0,
    error         TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
"""


@contextmanager
def _conn():
    con = sqlite3.connect(str(settings.DB_PATH), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=30000;")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.executescript(SCHEMA)


def create_job(filename):
    job_id = uuid.uuid4().hex
    now = time.time()
    with _conn() as con:
        con.execute(
            "INSERT INTO jobs (id, filename, status, created_at, updated_at)"
            " VALUES (?, ?, 'queued', ?, ?)",
            (job_id, filename, now, now),
        )
    return job_id


def get_job(job_id):
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
    return dict(row) if row else None


def update_job(job_id, **fields):
    if not fields:
        return
    fields["updated_at"] = time.time()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _conn() as con:
        con.execute(
            f"UPDATE jobs SET {cols} WHERE id=?",
            (*fields.values(), job_id),
        )


def set_pages_done(job_id, n):
    with _conn() as con:
        con.execute(
            "UPDATE jobs SET pages_done=?, updated_at=? WHERE id=?",
            (n, time.time(), job_id),
        )


def recover_stuck_jobs():
    """On worker startup: any job left 'processing' means a prior crash.
    Single worker, so it is safe to requeue them (page-level checkpoints
    make the rerun resume, not restart)."""
    with _conn() as con:
        con.execute(
            "UPDATE jobs SET status='queued', updated_at=? "
            "WHERE status='processing'",
            (time.time(),),
        )


def claim_next_job():
    """Atomically claim the oldest queued job. Returns the row dict or None."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM jobs WHERE status='queued' "
            "ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not row:
            return None
        n = con.execute(
            "UPDATE jobs SET status='processing', updated_at=? "
            "WHERE id=? AND status='queued'",
            (time.time(), row["id"]),
        ).rowcount
        if n == 0:
            return None
        return dict(row)


def expired_jobs(retention_days):
    if retention_days <= 0:
        return []
    cutoff = time.time() - retention_days * 86400
    with _conn() as con:
        rows = con.execute(
            "SELECT id FROM jobs WHERE status IN ('done','failed') "
            "AND updated_at < ?",
            (cutoff,),
        ).fetchall()
    return [r["id"] for r in rows]


def delete_job(job_id):
    with _conn() as con:
        con.execute("DELETE FROM jobs WHERE id=?", (job_id,))
