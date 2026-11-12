# =====================================================================
# A2M Digital Solutions - Makefile
#
#   make deploy    - full deployment (pull, build, up, verify)
#   make build     - build the Docker images
#   make up/down   - start / stop the services
#   make logs      - tail the logs
#   make status    - service status
#   make backup    - copy the SQLite database out of the container
#
# Uses Docker Compose v2 (`docker compose`). Compose v1 is end-of-life
# and is not installed by current Docker Engine packages.
# =====================================================================

APP_DIR    ?= $(HOME)/a2m-digital-solutions
COMPOSE    ?= docker compose -f docker-compose.prod.yml
BACKEND    ?= $(APP_DIR)/backend

.PHONY: deploy build up down logs restart test clean help pull status backup quick ssl-renew logs-backend logs-frontend certbot-issue

# Default target
help:
	@echo "A2M Digital Solutions - Deployment Commands"
	@echo ""
	@echo "Usage:"
	@echo "  make deploy     - Full deployment (pull, build, up, verify)"
	@echo "  make build      - Build Docker images"
	@echo "  make up         - Start services"
	@echo "  make down       - Stop services"
	@echo "  make restart    - Restart services"
	@echo "  make logs       - View logs"
	@echo "  make test       - Test API endpoints"
	@echo "  make clean      - Clean up everything"
	@echo "  make status     - Check service status"
	@echo "  make pull       - Pull latest code"
	@echo "  make backup     - Backup database"
	@echo "  make ssl-renew  - Renew the TLS certificate"
	@echo ""
	@echo "Override the checkout location with:  make deploy APP_DIR=/path/to/repo"

# Full deployment
deploy: pull build up test
	@echo "✅ Deployment complete!"

# Pull latest code
pull:
	@echo "📥 Pulling latest code..."
	@cd $(APP_DIR) && git stash push -- '*.py' '*.html' '*.yml' '*.yaml' '*.sh' '*.conf' '*.css' '*.js' >/dev/null 2>&1 || true
	@cd $(APP_DIR) && git pull --ff-only origin main

# Build images
build:
	@echo "🔨 Building Docker images..."
	docker build --no-cache -f backend/Dockerfile.prod -t a2m-backend ./backend
	docker build --no-cache -f Dockerfile.frontend -t a2m-frontend .

# Start services
up:
	@echo "🚀 Starting services..."
	@mkdir -p certbot/conf certbot/www
	@mkdir -p backend/data
	@chown 1000:1000 backend/data 2>/dev/null || chmod 0777 backend/data
	$(COMPOSE) up -d
	@sleep 5
	@$(MAKE) status

# Stop services
down:
	@echo "🛑 Stopping services..."
	$(COMPOSE) down

# Restart services
restart:
	@echo "🔄 Restarting services..."
	$(COMPOSE) restart

# View logs
logs:
	$(COMPOSE) logs -f

# Check service status
status:
	@echo "📊 Service Status:"
	@$(COMPOSE) ps

# Test the deployment - read-only checks only.
# The previous version POSTed a test inquiry to the LIVE production API,
# which inserted a real row into the database and sent a real email.
test:
	@echo "🧪 Testing API endpoints..."
	@echo "Checking backend health..."
	@$(COMPOSE) exec -T backend python -c "import httpx,sys; sys.exit(0 if httpx.get('http://localhost:8000/health', timeout=5).status_code==200 else 1)" \
		&& echo "✅ Backend healthy" || echo "❌ Backend FAILED"
	@echo "Checking frontend..."
	@$(COMPOSE) exec -T frontend wget --quiet --tries=1 --spider http://127.0.0.1/ \
		&& echo "✅ Frontend serving" || echo "❌ Frontend FAILED"
	@echo "Checking public site..."
	@curl -s -f --max-time 15 https://a2mdigitalsolutions.com/health >/dev/null \
		&& echo "✅ Public site healthy" \
		|| echo "⚠️  Public site not reachable yet (DNS/SSL may still be pending)"

# Clean up everything
clean:
	@echo "🧹 Cleaning up..."
	$(COMPOSE) down -v
	docker rm -f a2m-frontend a2m-backend a2m-certbot 2>/dev/null || true
	docker rmi a2m-frontend a2m-backend 2>/dev/null || true
	docker system prune -f

# Backup database
backup:
	@echo "💾 Backing up database..."
	@mkdir -p $(HOME)/backups
	docker cp a2m-backend:/app/data/inquiries.db $(HOME)/backups/inquiries-$(shell date +%Y%m%d-%H%M%S).db
	@echo "✅ Backup saved to $(HOME)/backups/"

# Quick deploy (pull + build + up)
quick: pull build up
	@echo "⚡ Quick deploy complete!"

# SSL certificate renewal
ssl-renew:
	@echo "🔐 Renewing SSL certificate..."
	$(COMPOSE) run --rm certbot renew --webroot -w /var/www/certbot --quiet
	@$(MAKE) restart

# First-time certificate issuance
certbot-issue:
	@echo "🔐 Requesting TLS certificate..."
	$(COMPOSE) run --rm certbot certonly --webroot -w /var/www/certbot \
		-d a2mdigitalsolutions.com -d www.a2mdigitalsolutions.com \
		--agree-tos -m $(EMAIL)
	@$(MAKE) restart

# View logs for a specific service
logs-backend:
	$(COMPOSE) logs -f backend

logs-frontend:
	$(COMPOSE) logs -f frontend
