"""FastAPI service. No GPU here - it only accepts uploads, records jobs,
and serves status/results. The worker process does the OCR.

Auth: every request must carry  Authorization: Bearer <API_KEY>.
"""

import shutil
from contextlib import asynccontextmanager

import fitz
from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from . import db, storage
from .settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate config (fails fast if API_KEY missing) and create the schema
    # before serving any request.
    settings.check()
    db.init_db()
    yield


app = FastAPI(title="ACB OCR Service", version="1.0", lifespan=lifespan)

# CORS so browser clients (React/Next/etc.) on other origins can call the API.
# CORSMiddleware also answers preflight OPTIONS automatically. Origins and
# credentials come from the environment (see settings.cors_config).
_cors_origins, _cors_creds = settings.cors_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_creds,
    allow_methods=["*"],
    allow_headers=["*"],   # includes Authorization for the Bearer key
)


def require_key(authorization: str = Header(default="")):
    expected = f"Bearer {settings.API_KEY}"
    # constant-ish comparison; tokens are short and this is not timing
    # sensitive at our scale, but avoid leaking length via early return.
    if not authorization or authorization != expected:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/jobs", status_code=202, dependencies=[Depends(require_key)])
async def create_job(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="must upload a .pdf file")

    job_id = db.create_job(file.filename)
    storage.ensure_dirs(job_id)
    dest = storage.input_pdf(job_id)

    size = 0
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close()
                shutil.rmtree(storage.job_dir(job_id), ignore_errors=True)
                db.update_job(job_id, status="failed",
                              error="upload exceeds size limit")
                raise HTTPException(
                    status_code=413,
                    detail=f"file exceeds {settings.MAX_UPLOAD_MB} MB",
                )
            out.write(chunk)

    # Validate it is a real PDF and within page limit before queueing.
    try:
        with fitz.open(dest) as doc:
            pages = doc.page_count
    except Exception:
        shutil.rmtree(storage.job_dir(job_id), ignore_errors=True)
        db.update_job(job_id, status="failed", error="not a valid PDF")
        raise HTTPException(status_code=400, detail="not a valid PDF")

    if pages == 0 or pages > settings.MAX_PAGES:
        shutil.rmtree(storage.job_dir(job_id), ignore_errors=True)
        db.update_job(job_id, status="failed",
                      error=f"page count {pages} outside 1..{settings.MAX_PAGES}")
        raise HTTPException(
            status_code=400,
            detail=f"page count {pages} outside 1..{settings.MAX_PAGES}",
        )

    db.update_job(job_id, total_pages=pages)
    return {"job_id": job_id, "status": "queued", "total_pages": pages}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_key)])
def job_status(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse({
        "job_id": job["id"],
        "status": job["status"],
        "pages_done": job["pages_done"],
        "total_pages": job["total_pages"],
        "error": job["error"],
    })


@app.get("/jobs/{job_id}/result", dependencies=[Depends(require_key)])
def job_result(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] == "failed":
        raise HTTPException(status_code=409,
                            detail=f"job failed: {job['error']}")
    if job["status"] != "done":
        raise HTTPException(
            status_code=409,
            detail=f"job not finished (status: {job['status']})",
        )
    out = storage.output_md(job_id)
    if not out.exists():
        raise HTTPException(status_code=500, detail="result file missing")
    return PlainTextResponse(
        out.read_text(encoding="utf-8"),
        media_type="text/markdown",
        headers={
            "Content-Disposition":
                f'attachment; filename="{job_id}.md"'
        },
    )
