#!/bin/sh
# =====================================================================
# A2M Digital Solutions - frontend entrypoint
#
# nginx refuses to start when ssl_certificate points at a file that does
# not exist. On a brand new server the Let's Encrypt certificate has not
# been issued yet, which would create a chicken-and-egg problem:
#   - certbot needs nginx running to answer the ACME challenge
#   - nginx needs the certificate to start
#
# This script breaks the loop: if the real certificate is missing it
# mints a temporary self-signed one so nginx can start and serve the
# ACME challenge over plain HTTP. certbot then replaces it with the real
# certificate, and a `docker compose restart frontend` picks it up.
# =====================================================================
set -e

CERT_NAME="a2mdigitalsolutions.com"
CERT_DIR="/etc/letsencrypt/live/${CERT_NAME}"

if [ ! -f "${CERT_DIR}/fullchain.pem" ] || [ ! -f "${CERT_DIR}/privkey.pem" ]; then
    echo "[a2m] No TLS certificate found at ${CERT_DIR}."
    echo "[a2m] Generating a temporary self-signed certificate so nginx can start."
    mkdir -p "${CERT_DIR}"
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
        -keyout "${CERT_DIR}/privkey.pem" \
        -out "${CERT_DIR}/fullchain.pem" \
        -subj "/CN=${CERT_NAME}" >/dev/null 2>&1
    echo "[a2m] Temporary certificate created. Issue the real one with:"
    echo "[a2m]   docker compose -f docker-compose.prod.yml run --rm certbot \\"
    echo "[a2m]     certonly --webroot -w /var/www/certbot \\"
    echo "[a2m]     -d ${CERT_NAME} -d www.${CERT_NAME} --agree-tos -m you@example.com"
    echo "[a2m]   docker compose -f docker-compose.prod.yml restart frontend"
else
    echo "[a2m] TLS certificate found at ${CERT_DIR}."
fi
