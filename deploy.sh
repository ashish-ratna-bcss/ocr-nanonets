#!/usr/bin/env bash
# One-command deploy for the ACB OCR service.
#   ./deploy.sh
# Prereqs on the host (one-time): Docker, Docker Compose v2, and the
# NVIDIA Container Toolkit (so containers can use the A4000).
set -euo pipefail

cd "$(dirname "$0")"

# 1. Ensure .env exists with an API key.
if [ ! -f .env ]; then
    echo "No .env found - creating from template."
    cp .env.example .env
    echo "!! Edit .env and set a real API_KEY, then re-run ./deploy.sh"
    exit 1
fi
if grep -q "change-me-to-a-long-random-secret" .env; then
    echo "!! API_KEY is still the placeholder. Edit .env and set a real secret."
    exit 1
fi

# 2. Pick the compose command.
if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    echo "Docker Compose not found. Install Docker + Compose v2." >&2
    exit 1
fi

# 3. Quick GPU sanity check (warn, don't block).
if ! docker info 2>/dev/null | grep -qi nvidia; then
    echo "WARNING: NVIDIA runtime not detected in Docker."
    echo "Install nvidia-container-toolkit or the worker will have no GPU."
fi

# 4. Build and start.
echo "Building and starting services..."
$DC up -d --build

echo
echo "Done. Services:"
$DC ps
echo
echo "First start downloads the model (~7GB) into the hf-cache volume."
echo "Watch the worker load it:   $DC logs -f worker"
echo "Health check:               curl -k https://localhost/healthz"
