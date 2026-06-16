#!/usr/bin/env bash
# Install the ACB OCR stack as a systemd service so it starts on boot and
# survives SSH logout / instance restarts. Run once, with sudo, after the
# host has Docker + Compose v2 + NVIDIA Container Toolkit installed.
#
#   sudo ./install-service.sh
#
# Idempotent: re-running updates the unit and restarts the service.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_SRC="$REPO_DIR/systemd/acb-ocr.service"
UNIT_DST="/etc/systemd/system/acb-ocr.service"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo:  sudo ./install-service.sh" >&2
    exit 1
fi

if [ ! -f "$REPO_DIR/.env" ]; then
    echo "No .env found. Create it first:  cp .env.example .env  (set API_KEY)" >&2
    exit 1
fi
if grep -q "change-me-to-a-long-random-secret" "$REPO_DIR/.env"; then
    echo "API_KEY is still the placeholder. Edit .env and set a real secret." >&2
    exit 1
fi

# Make sure Docker itself starts on boot, otherwise our unit has nothing to
# talk to after a reboot.
systemctl enable docker >/dev/null 2>&1 || true

echo "Installing systemd unit -> $UNIT_DST (WorkingDirectory=$REPO_DIR)"
sed "s#__WORKDIR__#$REPO_DIR#g" "$UNIT_SRC" > "$UNIT_DST"

systemctl daemon-reload
systemctl enable acb-ocr.service
systemctl restart acb-ocr.service

echo
echo "Done. The stack now starts automatically on boot."
echo "  Status:   systemctl status acb-ocr"
echo "  Logs:     journalctl -u acb-ocr -f"
echo "  Stack:    docker compose -f $REPO_DIR/docker-compose.yml ps"
