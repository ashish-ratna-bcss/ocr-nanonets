"""Filesystem layout for a job. Shared by API and worker.

/data/{job_id}/
    input.pdf            uploaded file
    pages/{n}.md         per-page checkpoint (n is 1-based)
    output.md            final assembled result
"""

from .settings import settings


def job_dir(job_id):
    d = settings.DATA_DIR / job_id
    return d


def input_pdf(job_id):
    return job_dir(job_id) / "input.pdf"


def pages_dir(job_id):
    return job_dir(job_id) / "pages"


def page_md(job_id, page_no):
    return pages_dir(job_id) / f"{page_no}.md"


def output_md(job_id):
    return job_dir(job_id) / "output.md"


def ensure_dirs(job_id):
    pages_dir(job_id).mkdir(parents=True, exist_ok=True)
