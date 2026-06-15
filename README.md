# ACB OCR Service

OCR API for Anti-Corruption Bureau (Telangana) scanned case files. Wraps
**Nanonets-OCR2-3B** (Qwen2.5-VL) and returns structured Markdown. Built for
large PDFs (150-200 pages) on a single NVIDIA RTX A4000.

> **Sensitive data.** These are real law-enforcement files. The service runs
> on a private network behind TLS + an API key, auto-deletes finished jobs
> after a retention window, and never silently fabricates text (faint pages
> are flagged for manual review).

## Architecture

```
Next app ──HTTPS + API key──> nginx ──> FastAPI (api)        Worker (GPU)
                                          │  enqueue            loads model once
                                          │  status/result      OCR page-by-page
                                          └──── SQLite + /data volume ────┘
```

- **api** – accepts uploads, tracks jobs, serves results. No GPU.
- **worker** – loads the model once, processes one job at a time (single GPU),
  checkpoints every page so a restart resumes instead of restarting.
- **nginx** – public TLS endpoint, large-upload support.

Jobs are **async**: submit a PDF, get a `job_id`, poll until `done`, fetch the
`.md`.

## Deploy (turnkey)

Host prereqs (one-time): Docker, Docker Compose v2, NVIDIA Container Toolkit.

```bash
cp .env.example .env          # set a strong API_KEY
./deploy.sh
```

First start downloads the model (~7GB) into a persistent volume. Watch it:

```bash
docker compose logs -f worker     # "Model loaded. Worker ready."
curl -k https://localhost/healthz
```

That's it — no code edits, no manual steps.

## API

All requests need `Authorization: Bearer <API_KEY>`.

| Method | Path | Body / returns |
|--------|------|----------------|
| `POST` | `/jobs` | multipart `file=@doc.pdf` → `{job_id, status, total_pages}` |
| `GET`  | `/jobs/{id}` | `{status, pages_done, total_pages, error}` |
| `GET`  | `/jobs/{id}/result` | the `.md` (when `status=done`), else `409` |
| `GET`  | `/healthz` | liveness |

`status`: `queued` → `processing` → `done` \| `failed`.

### curl example

```bash
KEY=your-api-key
# submit
JOB=$(curl -sk -H "Authorization: Bearer $KEY" \
     -F file=@case.pdf https://server/jobs | jq -r .job_id)
# poll
curl -sk -H "Authorization: Bearer $KEY" https://server/jobs/$JOB
# fetch result when done
curl -sk -H "Authorization: Bearer $KEY" https://server/jobs/$JOB/result -o case.md
```

### Next.js (App Router) example

```ts
// app/api/ocr/route.ts  (server-side; keep the key server-only)
const BASE = process.env.OCR_BASE_URL!;      // https://server
const KEY  = process.env.OCR_API_KEY!;

export async function submit(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${BASE}/jobs`, {
    method: "POST",
    headers: { Authorization: `Bearer ${KEY}` },
    body: fd,
  });
  return r.json(); // { job_id, status, total_pages }
}

export async function poll(jobId: string) {
  const r = await fetch(`${BASE}/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${KEY}` },
  });
  return r.json(); // { status, pages_done, total_pages }
}

export async function result(jobId: string) {
  const r = await fetch(`${BASE}/jobs/${jobId}/result`, {
    headers: { Authorization: `Bearer ${KEY}` },
  });
  return r.text(); // structured markdown
}
```

Poll every ~10s; a 200-page file takes roughly 20-40 min on one A4000.

> Self-signed TLS by default → server-to-server fetches must trust it. Either
> install the generated cert as a CA on the Next host, or (less ideal) set
> `NODE_TLS_REJECT_UNAUTHORIZED=0` for that call. For a real domain, drop a
> Let's Encrypt `server.crt`/`server.key` into the `certs` volume.

## Configuration

See `.env.example`. Only `API_KEY` is required.

| Var | Default | Meaning |
|-----|---------|---------|
| `API_KEY` | – | shared secret (required) |
| `RETENTION_DAYS` | 7 | auto-delete finished jobs after N days (0 = keep) |
| `RENDER_DPI` | 300 | page rasterisation DPI |
| `MAX_PAGES` | 300 | reject larger PDFs |
| `MAX_UPLOAD_MB` | 300 | reject larger uploads |

## Local CLI (no server)

`python hf_ocr.py` still runs a single PDF through the same core for quick
local checks. It uses `app/ocr_core.py`, so behaviour matches the service.

## Notes / limits

- One job at a time (single GPU). Concurrent submits queue.
- Faint/skewed pages may be flagged **NEEDS MANUAL REVIEW** rather than
  guessed — intended, for evidence integrity.
- Telugu: printed handled; handwritten Telugu is unreliable.
