#!/bin/bash
# =====================================================================
# A2M Digital Solutions - quick deploy (pull + rebuild + restart)
#
#   ./deploy-quick.sh
#
# Uses Docker Compose v2 (`docker compose`). Compose v1 is end-of-life
# and is not installed by current Docker Engine packages.
# =====================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/a2m-digital-solutions}"
COMPOSE_FILE="docker-compose.prod.yml"

echo "🚀 A2M Digital Solutions - Quick Deploy"

cd "$APP_DIR" 2>/dev/null || {
    echo "📥 Cloning repository..."
    git clone https://github.com/anantamisal/a2m-digital-solutions.git "$APP_DIR"
    cd "$APP_DIR"
}

# Detect Docker Compose command: prefer `docker compose` (v2 plugin),
# fall back to `docker-compose` (v1 binary).
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "ERROR: neither 'docker compose' nor 'docker-compose' found" >&2
  exit 1
fi
echo "Using compose command: $COMPOSE_CMD"

compose() { $COMPOSE_CMD -f "$COMPOSE_FILE" "$@"; }

# Scoped stash: a blanket `git stash` used to revert the tracked SQLite
# database and discard live inquiries on every deploy.
git stash push -- '*.py' '*.html' '*.yml' '*.yaml' '*.sh' '*.conf' '*.css' '*.js' >/dev/null 2>&1 || true
git pull --ff-only origin main

if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    echo "⚠️  Edit backend/.env - set ADMIN_PASSWORD and your API keys!"
fi

mkdir -p certbot/conf certbot/www

# The inquiry database lives in ./backend/data, which is bind-mounted
# into the container. Docker creates a missing bind-mount source as
# ROOT, and the container runs as the non-root user with UID 1000 - so
# the database could not be written. Create it as the host user first.
mkdir -p backend/data
chown 1000:1000 backend/data 2>/dev/null || chmod 0777 backend/data

compose down -v >/dev/null 2>&1 || true
docker rm -f a2m-frontend a2m-backend a2m-certbot >/dev/null 2>&1 || true
docker rmi a2m-frontend a2m-backend >/dev/null 2>&1 || true

docker build --no-cache -f backend/Dockerfile.prod -t a2m-backend ./backend
docker build --no-cache -f Dockerfile.frontend -t a2m-frontend .

compose up -d

sleep 5
echo "✅ Deployed! Check: https://a2mdigitalsolutions.com"
compose ps
