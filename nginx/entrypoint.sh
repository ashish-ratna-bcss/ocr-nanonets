#!/bin/sh
# Auto-generate a self-signed TLS cert on first start so the service is
# encrypted with zero manual steps. Runs via nginx's /docker-entrypoint.d/.
#
# For a browser-trusted cert (a real domain), replace server.crt/server.key
# in the `certs` volume with a Let's Encrypt pair - see README.
set -e

CERT_DIR=/etc/nginx/certs
CRT="$CERT_DIR/server.crt"
KEY="$CERT_DIR/server.key"

mkdir -p "$CERT_DIR"

if [ ! -f "$CRT" ] || [ ! -f "$KEY" ]; then
    echo "[tls] generating self-signed certificate..."
    apk add --no-cache openssl >/dev/null 2>&1 || true
    openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
        -keyout "$KEY" -out "$CRT" \
        -subj "/CN=acb-ocr" \
        -addext "subjectAltName=DNS:acb-ocr,IP:127.0.0.1"
    echo "[tls] certificate created."
fi
