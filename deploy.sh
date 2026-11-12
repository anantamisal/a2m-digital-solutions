#!/bin/bash
# =====================================================================
# A2M Digital Solutions - production deployment (Oracle Cloud)
#
#   ./deploy.sh
#
# Run as the user that owns the checkout (the 'ubuntu' user on the
# Oracle instance). Override the checkout location with APP_DIR if the
# repository does not live at ~/a2m-digital-solutions.
# =====================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/a2m-digital-solutions}"
COMPOSE_FILE="docker-compose.prod.yml"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

cd "$APP_DIR"

compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

log_info "Starting A2M Digital Solutions deployment..."

# --- 1. Pull the latest code ------------------------------------------
# The stash is SCOPED to source files. A blanket `git stash` used to
# revert the tracked SQLite database and silently discard every inquiry
# received since the last commit.
log_info "Pulling latest code from GitHub..."
git stash push -- '*.py' '*.html' '*.yml' '*.yaml' '*.sh' '*.conf' '*.css' '*.js' >/dev/null 2>&1 || true
git pull --ff-only origin main

# --- 2. Configuration --------------------------------------------------
if [ ! -f backend/.env ]; then
    log_warn "backend/.env not found - creating it from the example."
    log_warn "You MUST edit backend/.env and set ADMIN_PASSWORD before going live."
    cp backend/.env.example backend/.env
fi

# The compose file mounts these directories; Docker would otherwise
# create them as root and the certificate renewal would fail.
mkdir -p certbot/conf certbot/www

# The inquiry database lives in ./backend/data, which is bind-mounted
# into the container. Docker creates a missing bind-mount source as
# ROOT, and the container runs as the non-root user with UID 1000 - so
# the database could not be written. Create it as the host user first.
mkdir -p backend/data
chown 1000:1000 backend/data 2>/dev/null || chmod 0777 backend/data
echo "backend/data owner: $(stat -c '%U:%G (%a)' backend/data)"

if grep -qE '^ADMIN_PASSWORD=(admin123|change-me.*|)\s*$' backend/.env 2>/dev/null; then
    log_warn "ADMIN_PASSWORD is still the default in backend/.env - change it before going live."
fi

# --- 3. Rebuild the images --------------------------------------------
log_info "Cleaning up old containers..."
compose down -v >/dev/null 2>&1 || true
docker rm -f a2m-frontend a2m-backend a2m-certbot >/dev/null 2>&1 || true
docker rmi a2m-frontend a2m-backend >/dev/null 2>&1 || true

log_info "Building backend image..."
docker build --no-cache -f backend/Dockerfile.prod -t a2m-backend ./backend

log_info "Building frontend image..."
docker build --no-cache -f Dockerfile.frontend -t a2m-frontend .

# --- 4. Start the services ---------------------------------------------
log_info "Starting services..."
compose up -d

log_info "Waiting for services to start..."
sleep 10

# --- 5. Verify ----------------------------------------------------------
log_info "Verifying deployment..."

# The backend is only reachable inside the a2m-network bridge, so the
# health check runs inside the container rather than from the host.
if compose exec -T backend python -c \
   "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health', timeout=5).status_code==200 else 1)" \
   >/dev/null 2>&1; then
    log_info "✅ Backend API healthy"
else
    log_error "❌ Backend API not responding"
    compose logs backend
    exit 1
fi

if compose exec -T frontend wget --quiet --tries=1 --spider http://127.0.0.1/ >/dev/null 2>&1; then
    log_info "✅ Frontend serving"
else
    log_error "❌ Frontend not responding"
    compose logs frontend
    exit 1
fi

# /health is the real backend route - there is no /api/health.
if curl -s -f --max-time 15 https://a2mdigitalsolutions.com/health >/dev/null 2>&1; then
    log_info "✅ HTTPS site healthy"
else
    log_warn "⚠️ https://a2mdigitalsolutions.com/health not reachable yet."
    log_warn "   If the certificate has not been issued yet, run:"
    log_warn "   docker compose -f $COMPOSE_FILE run --rm certbot certonly --webroot -w /var/www/certbot \\"
    log_warn "     -d a2mdigitalsolutions.com -d www.a2mdigitalsolutions.com --agree-tos -m you@example.com"
    log_warn "   docker compose -f $COMPOSE_FILE restart frontend"
fi

# --- 6. Status ----------------------------------------------------------
log_info "Service status:"
compose ps

echo ""
log_info "🎉 Deployment complete!"
echo ""
echo "🌐 Site:        https://a2mdigitalsolutions.com"
echo "🔧 Admin panel: https://a2mdigitalsolutions.com/admin.html"
echo "📚 API docs:    https://a2mdigitalsolutions.com/docs"
echo ""
ADMIN_USER_NAME=$(grep -E '^ADMIN_USERNAME=' backend/.env 2>/dev/null | cut -d= -f2)
ADMIN_USER_NAME="${ADMIN_USER_NAME:-admin}"
log_info "Admin username: ${ADMIN_USER_NAME}"
log_warn "Admin password: whatever you set as ADMIN_PASSWORD in backend/.env"
log_warn "It is NOT printed here on purpose - never commit that file."
echo ""
