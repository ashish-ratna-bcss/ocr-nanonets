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

## Deploy on AWS EC2 (production)

One-time setup on a fresh GPU instance (e.g. `g5.xlarge` — Ubuntu 22.04 +
NVIDIA driver). After this, the API survives reboots, crashes, and SSH logout
with zero manual steps.

```bash
# 1. Host prereqs (one-time)
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2
# NVIDIA Container Toolkit (so the worker sees the GPU):
#   https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

# 2. Get the code + config
git clone <repo> acb-ocr && cd acb-ocr
cp .env.example .env
nano .env            # set a strong API_KEY (openssl rand -hex 32) + CORS_ORIGINS

# 3. Install as a boot-persistent systemd service
sudo ./install-service.sh
```

`install-service.sh` writes `/etc/systemd/system/acb-ocr.service`, enables
Docker + the unit on boot, and starts the stack. From now on:

| You do | What happens automatically |
|--------|----------------------------|
| Stop/start the EC2 instance | service comes back up on boot |
| App crashes | container restarts (`restart: unless-stopped`) |
| Close SSH | service keeps running (managed by systemd, not your shell) |
| Edit `.env` | `sudo systemctl restart acb-ocr` to apply |

Operate it:

```bash
systemctl status acb-ocr        # is it up?
journalctl -u acb-ocr -f        # service-level logs
docker compose logs -f worker   # model load / OCR progress
sudo systemctl restart acb-ocr  # apply .env changes
```

### Elastic IP (stable public address)

A default EC2 public IP changes every stop/start. Attach an Elastic IP so the
address is permanent:

1. EC2 console → **Elastic IPs** → **Allocate Elastic IP address**.
2. Select it → **Actions → Associate** → choose the instance.
3. Clients hit `https://<elastic-ip>/…`. It stays the same across reboots.

(No domain needed. TLS is a self-signed cert by default — see the TLS note
under the Next.js example.)

### Security group (firewall) rules

Inbound rules on the instance's security group:

| Type | Protocol | Port | Source | Why |
|------|----------|------|--------|-----|
| HTTPS | TCP | 443 | `0.0.0.0/0` (or your app/CIDR allowlist) | API traffic |
| HTTP | TCP | 80 | `0.0.0.0/0` | redirect to HTTPS |
| SSH | TCP | 22 | **your IP only** | admin access |

Sensitive data: restrict 443 to known client IPs/CIDRs where possible rather
than opening it to the whole internet. Outbound: leave default (allow all) so
the worker can download the model from Hugging Face on first start.

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
| `CORS_ORIGINS` | `*` | allowed browser origins; `*` or comma-separated allowlist |
| `CORS_ALLOW_CREDENTIALS` | `false` | allow cookies (ignored when origins = `*`) |
| `HTTPS_PORT` | 443 | host port for TLS |
| `HTTP_PORT` | 80 | host port for plain HTTP (redirects to HTTPS) |
| `RETENTION_DAYS` | 7 | auto-delete finished jobs after N days (0 = keep) |
| `RENDER_DPI` | 300 | page rasterisation DPI |
| `MAX_PAGES` | 300 | reject larger PDFs |
| `MAX_UPLOAD_MB` | 300 | reject larger uploads |

### CORS (browser clients)

Server-to-server callers (Next.js route handlers, mobile backends) don't need
CORS. Browser apps calling the API **directly** do. Configure via `.env`:

```env
# development — any origin
CORS_ORIGINS=*

# production — explicit allowlist
CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

Preflight `OPTIONS` requests are answered automatically, and the
`Authorization` header (the Bearer key) is allowed, so API-key auth works
across origins. The spec forbids credentials with a wildcard origin, so
`CORS_ALLOW_CREDENTIALS` is ignored while `CORS_ORIGINS=*`.

## Local CLI (no server)

`python hf_ocr.py` still runs a single PDF through the same core for quick
local checks. It uses `app/ocr_core.py`, so behaviour matches the service.

## Notes / limits

- One job at a time (single GPU). Concurrent submits queue.
- Faint/skewed pages may be flagged **NEEDS MANUAL REVIEW** rather than
  guessed — intended, for evidence integrity.
- Telugu: printed handled; handwritten Telugu is unreliable.
