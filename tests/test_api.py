"""API lifecycle tests with a stubbed worker (no GPU).

We exercise the full job flow by driving the DB the way the worker would,
so these run on any machine without torch/CUDA.
"""

import io

import fitz
import pytest
from fastapi.testclient import TestClient

from app import db, storage
from app.api import app

KEY = {"Authorization": "Bearer test-key"}
client = TestClient(app)


def _make_pdf(pages=2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Test page {i + 1}")
    buf = doc.tobytes()
    doc.close()
    return io.BytesIO(buf)


def test_health():
    assert client.get("/healthz").json()["ok"] is True


def test_auth_required():
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 401


def test_unknown_job_404():
    r = client.get("/jobs/nope", headers=KEY)
    assert r.status_code == 404


def test_reject_non_pdf():
    r = client.post(
        "/jobs", headers=KEY,
        files={"file": ("x.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert r.status_code == 400


def test_full_lifecycle():
    # submit
    r = client.post(
        "/jobs", headers=KEY,
        files={"file": ("case.pdf", _make_pdf(2), "application/pdf")},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert r.json()["total_pages"] == 2

    # result not ready yet
    assert client.get(f"/jobs/{job_id}/result", headers=KEY).status_code == 409

    # simulate the worker finishing
    storage.ensure_dirs(job_id)
    storage.output_md(job_id).write_text("## Page 1\n\nhello", encoding="utf-8")
    db.update_job(job_id, status="done", pages_done=2)

    # status reflects done
    s = client.get(f"/jobs/{job_id}", headers=KEY).json()
    assert s["status"] == "done" and s["pages_done"] == 2

    # result downloads
    res = client.get(f"/jobs/{job_id}/result", headers=KEY)
    assert res.status_code == 200
    assert "hello" in res.text
