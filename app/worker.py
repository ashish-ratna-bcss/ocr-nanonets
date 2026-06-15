"""GPU worker. Loads the model once, then drains the job queue one job at a
time (single A4000 = one model in VRAM). Per-page checkpoints make a job
resume after a crash/restart instead of starting over.

Run:  python -m app.worker
"""

import time
import traceback

import fitz

from . import db, storage
from .ocr_core import OCREngine
from .settings import settings


def assemble_output(job_id, total_pages):
    """Concatenate per-page checkpoints into the final structured .md."""
    parts = []
    for n in range(1, total_pages + 1):
        p = storage.page_md(job_id, n)
        body = p.read_text(encoding="utf-8") if p.exists() else \
            "> **PAGE MISSING** - not produced."
        parts.append(f"## Page {n}\n\n{body}")
    storage.output_md(job_id).write_text(
        "\n\n---\n\n".join(parts), encoding="utf-8"
    )


def process_job(engine, job):
    job_id = job["id"]
    total = job["total_pages"]
    storage.ensure_dirs(job_id)
    pdf = storage.input_pdf(job_id)

    with fitz.open(pdf) as doc:
        total = total or doc.page_count
        db.update_job(job_id, total_pages=total)
        done = 0
        for idx in range(total):
            page_no = idx + 1
            checkpoint = storage.page_md(job_id, page_no)
            if checkpoint.exists():
                done = page_no
                db.set_pages_done(job_id, done)
                continue  # resume: already transcribed before a restart
            try:
                md = engine.ocr_pdf_page(doc, idx)
            except Exception as e:  # one bad page must not kill the job
                md = (
                    f"> **PAGE FAILED** - OCR error, manual review needed. "
                    f"({type(e).__name__}: {e})"
                )
            checkpoint.write_text(md, encoding="utf-8")
            done = page_no
            db.set_pages_done(job_id, done)
            print(f"  job {job_id[:8]} page {page_no}/{total}", flush=True)

    assemble_output(job_id, total)
    db.update_job(job_id, status="done", pages_done=total)
    print(f"job {job_id[:8]} done ({total} pages)", flush=True)


def cleanup(retention_days):
    import shutil
    for job_id in db.expired_jobs(retention_days):
        shutil.rmtree(storage.job_dir(job_id), ignore_errors=True)
        db.delete_job(job_id)


def main():
    settings.check()
    db.init_db()
    db.recover_stuck_jobs()

    print("Loading OCR model (one-time)...", flush=True)
    engine = OCREngine(
        model_id=settings.MODEL_ID,
        dpi=settings.RENDER_DPI,
    )
    print("Model loaded. Worker ready.", flush=True)

    last_cleanup = 0.0
    while True:
        # Periodic retention cleanup (hourly).
        if time.time() - last_cleanup > 3600:
            try:
                cleanup(settings.RETENTION_DAYS)
            except Exception:
                traceback.print_exc()
            last_cleanup = time.time()

        job = db.claim_next_job()
        if not job:
            time.sleep(settings.POLL_SECONDS)
            continue
        try:
            process_job(engine, job)
        except Exception as e:
            traceback.print_exc()
            db.update_job(job["id"], status="failed",
                          error=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
