# A2M Digital Solutions - Complete Deployment Documentation

**Version:** 2.0
**Last Updated:** 2026-11-10
**Environment:** Oracle Cloud Free Tier (ARM 4 OCPU, 24GB RAM)
**Domain:** a2mdigitalsolutions.com
**Repository:** https://github.com/anantamisal/a2m-digital-solutions
**Server path:** `/home/ubuntu/a2m-digital-solutions` (user `ubuntu`)

> **Version 2.0 changed the deployment model.** Docker Compose **v2** (`docker compose`) replaces the
> retired v1 binary, the stack is now built by `docker-compose.prod.yml` (nginx + FastAPI + certbot),
> the admin dashboard was rewritten with a working login and a voice AI Coach, and the visitor
> counter now uses an explicit tracking endpoint. Sections that changed are marked **[v2]**.

---

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Infrastructure Setup](#infrastructure-setup)
3. [Application Architecture](#application-architecture)
4. [Deployment Pipeline](#deployment-pipeline)
5. [Configuration Management](#configuration-management)
6. [AI Agent Configuration](#ai-agent-configuration)
7. [SSL/TLS Certificates](#ssltls-certificates)
8. [Email Configuration](#email-configuration)
9. [Database](#database)
10. [Admin Dashboard & AI Coach](#admin-dashboard--ai-coach)
11. [Visitor Tracking](#visitor-tracking)
12. [Monitoring & Maintenance](#monitoring--maintenance)
13. [Troubleshooting Guide](#troubleshooting-guide)
14. [Rollback Procedure](#rollback-procedure)
15. [Security Checklist](#security-checklist)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Oracle Cloud Free Tier                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Ubuntu 22.04 (ARM 4 OCPU, 24GB RAM)            │  │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │  │
│  │  │   Frontend  │    │   Backend   │    │   Database   │    │  │
│  │  │   (Nginx)   │◄───│  (FastAPI)  │◄───│  (SQLite)   │    │  │
│  │  │  Port 80/443│    │  Port 8000  │    │  inquiries.db│    │  │
│  │  │  (a2m-      │    │ (internal   │    │ (bind mount  │    │  │
│  │  │  frontend)  │    │  only)      │    │  ./backend/  │    │  │
│  │  └─────────────┘    └─────────────┘    │   data)      │    │  │
│  │         ▲                   ▲           └─────────────┘    │  │
│  │         │                   │                  ▲           │  │
│  │  ┌──────┴───────────────────┴──────────────────┴──────┐  │  │
│  │  │              Docker Network (a2m-network)              │  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────────────┐  │  │
│  │  │  certbot (a2m-certbot) — renews every 12h, webroot   │  │  │
│  │  └──────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     External Services                            │
│  ┌─────────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Cloudflare DNS │  │  Gmail SMTP │  │  Let's Encrypt SSL  │ │
│  │  (DNS Only)     │  │  (Port 587) │  │  (Auto-renewal)     │ │
│  └─────────────────┘  └─────────────┘  └─────────────────────┘ │
│  ┌─────────────────┐  ┌─────────────┐                           │
│  │  Pollinations   │  │ Edge TTS    │  ← optional, keyless     │
│  │  (keyless LLM)  │  │ (keyless)   │                           │
│  └─────────────────┘  └─────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

**Key Specifications:**
- **Compute:** Oracle Cloud Free Tier - ARM Ampere A1 (4 OCPU, 24GB RAM)
- **OS:** Ubuntu 22.04 LTS
- **Container Runtime:** Docker Engine 29.x + **Docker Compose v2** (the `docker compose` plugin)
- **Web Server:** Nginx (Frontend container) + Uvicorn (Backend container)
- **Database:** SQLite (`backend/data/inquiries.db`, bind-mounted into the backend container)
- **SSL:** Let's Encrypt (auto-renewal via the `certbot` compose service)

> ⚠️ **Compose v2 only [v2].** Compose v1 (the hyphenated `docker-compose` binary) reached end of
> life in January 2023 and is **not bundled** with modern Docker Engine. On a fresh Oracle instance
> the `docker-compose` command does not exist. Every command in this document uses `docker compose`.
> Verify the plugin is present with `docker compose version`; if it is missing, install it with
> `sudo apt-get install docker-compose-plugin`.

---

## ☁️ Infrastructure Setup

### Oracle Cloud Instance
```bash
# Instance Details
Shape: VM.Standard.A1.Flex (ARM Ampere A1)
OCPU: 4 (max free tier)
Memory: 24 GB (max free tier)
Boot Volume: 50 GB
VCN: a2m-digital-solutions-vcn
Subnet: Public subnet (10.0.0.0/24)
Public IP: 140.238.242.134
```

### Security Lists (Firewall)
| Rule | Source | Protocol | Port | Description |
|------|--------|----------|------|-------------|
| 1 | 0.0.0.0/0 | TCP | 22 | SSH Access |
| 2 | 0.0.0.0/0 | TCP | 80 | HTTP (redirect to HTTPS) + ACME challenge |
| 3 | 0.0.0.0/0 | TCP | 443 | HTTPS |

> The backend publishes **no host port** — it is reachable only on the internal Docker network.
> There is no need to open 8000 in the security list. **[v2]**

### SSH Access
```bash
# SSH Key Location (local)
~/.ssh/oracle_a2m.key

# SSH Command
ssh -i ~/.ssh/oracle_a2m.key ubuntu@140.238.242.134

# Server User: ubuntu (default for Ubuntu on Oracle)
# Repo path: /home/ubuntu/a2m-digital-solutions
```

### First-Time Server Setup
```bash
ssh -i ~/.ssh/oracle_a2m.key ubuntu@140.238.242.134

# Docker Engine + Compose v2 plugin
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
newgrp docker

# Confirm the plugin (must print a v2.x version)
docker compose version

# Clone the repo
git clone https://github.com/anantamisal/a2m-digital-solutions.git /home/ubuntu/a2m-digital-solutions
cd /home/ubuntu/a2m-digital-solutions
```

---

## 🐳 Application Architecture

### Docker Containers

| Container | Service | Host Ports | Purpose |
|-----------|---------|-----------|---------|
| `a2m-frontend` | `frontend` | 80, 443 | Nginx + static files + API reverse proxy |
| `a2m-backend` | `backend` | none (`expose: 8000`) | FastAPI / Uvicorn application |
| `a2m-certbot` | `certbot` | none | Renews the Let's Encrypt certificate every 12h |

### Docker Compose (Production) — `docker-compose.prod.yml` [v2]
```yaml
services:
  backend:
    image: a2m-backend:latest
    container_name: a2m-backend
    restart: unless-stopped
    build:
      context: ./backend
      dockerfile: Dockerfile.prod
    expose:
      - "8000"                     # internal only - no host port
    volumes:
      - ./backend/data:/app/data   # the inquiry database lives here
      - ./backend/.env:/app/.env:ro
    environment:
      DATABASE_URL: sqlite:///./data/inquiries.db
    networks:
      - a2m-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    image: a2m-frontend:latest
    container_name: a2m-frontend
    restart: unless-stopped
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - a2m-network

  certbot:
    image: certbot/certbot:latest
    container_name: a2m-certbot
    restart: unless-stopped
    volumes:
      - ./certbot/conf:/etc/letsencrypt
      - ./certbot/www:/var/www/certbot
    entrypoint: >
      sh -c "trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot --quiet; sleep 12h & wait $${!}; done;"
    networks:
      - a2m-network

networks:
  a2m-network:
    name: a2m-network
```

### Frontend (Nginx) Configuration — `nginx.conf` [v2]

```nginx
upstream a2m_backend {
    server backend:8000;
    keepalive 16;
}

server {
    listen 80;
    server_name a2mdigitalsolutions.com www.a2mdigitalsolutions.com;

    # ACME HTTP-01 challenge must stay on plain HTTP
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name a2mdigitalsolutions.com www.a2mdigitalsolutions.com;

    ssl_certificate     /etc/letsencrypt/live/a2mdigitalsolutions.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/a2mdigitalsolutions.com/privkey.pem;

    client_max_body_size 25m;      # audio uploads to /api/ai/transcribe
    proxy_read_timeout 90s;        # must exceed NVIDIA_TIMEOUT (60s)

    # ---- API traffic ----
    location /api/ {
        proxy_pass http://a2m_backend;      # NO trailing slash, NO URI part
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # ---- Legacy /admin/* aliases ----
    location /admin/ {
        proxy_pass http://a2m_backend;      # NO trailing slash
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # ---- Backend docs & health, proxied explicitly ----
    location = /health        { proxy_pass http://a2m_backend/health; }
    location = /docs          { proxy_pass http://a2m_backend/docs; }
    location = /redoc         { proxy_pass http://a2m_backend/redoc; }
    location = /openapi.json  { proxy_pass http://a2m_backend/openapi.json; }

    # ---- Static site ----
    location = /admin.html { try_files /admin.html =404; }
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

> ⚠️ **`proxy_pass` must have NO trailing slash and no URI part.**
> `proxy_pass http://a2m_backend;` preserves the request path exactly.
> `proxy_pass http://a2m_backend/;` (with a slash) or `proxy_pass http://a2m_backend/api/;`
> rewrites the path and **breaks every `/api/*` route**. This was the root cause of the original
> 404-on-`/api` outage.

#### What each nginx location serves

| Location | Served by | Notes |
|----------|-----------|-------|
| `/` | nginx (static `index.html`) | The backend never sees page requests — see [Visitor Tracking](#visitor-tracking) |
| `/admin.html` | nginx (static file) | The dashboard is a static page; only its `/api/*` calls are proxied |
| `/api/*` | FastAPI backend | Public site + admin API + AI agent |
| `/admin/*` | FastAPI backend | Legacy aliases for the admin API (e.g. `/admin/login`, `/admin/stats`) |
| `/health`, `/docs`, `/redoc`, `/openapi.json` | FastAPI backend | Proxied explicitly because they are not under `/api/` |

> **Note on `/admin/`:** the rule is a **prefix** match, so `/admin/login`, `/admin/stats` and
> `/admin/inquiries` all reach the backend. `admin.html` (no slash) is a *static file* and is served
> by the `location = /admin.html` rule instead. Do not rename either one.

### Static Assets Served by the Frontend Container
`Dockerfile.frontend` copies: `index.html`, `admin.html`, `company_logo_mark.png`,
`company_logo.png`, `company_logo1.png`, `styles.css`, `script.js`, `nginx.conf`,
`docker-entrypoint.sh`.

> `company_logo_mark.png` is the transparent blue/teal wordmark used on both the public site and the
> admin console. `company_logo1.png` is fully opaque (white background) and is **not** used in the
> admin sidebar.

---

## 🚀 Deployment Pipeline

### Manual Deployment (Current) [v2]
```bash
# 1. SSH into the server
ssh -i ~/.ssh/oracle_a2m.key ubuntu@140.238.242.134

# 2. Go to the repo
cd /home/ubuntu/a2m-digital-solutions

# 3. Deploy (this pulls, rebuilds both images, restarts, and health-checks)
./deploy.sh
```

### What `deploy.sh` Does [v2]
```bash
set -euo pipefail
APP_DIR="${APP_DIR:-$HOME/a2m-digital-solutions}"      # not a hard-coded cd
compose() { docker compose -f docker-compose.prod.yml "$@"; }

# 1. Scoped stash — source files ONLY, never *.db
git stash push -- '*.py' '*.html' '*.yml' '*.yaml' '*.sh' '*.conf' '*.css' '*.js' || true

# 2. Fast-forward only
git pull --ff-only

# 3. Build both images
compose build

# 4. Restart
compose up -d

# 5. Health-check the backend *inside* the container
compose exec -T backend python -c "import httpx; httpx.get('http://127.0.0.1:8000/health')"

# 6. Health-check the frontend through the proxy
wget --spider -q https://a2mdigitalsolutions.com/

# 7. Warn if ADMIN_PASSWORD is still the default; print the username, never the password
```

> ⚠️ **The stash is scoped on purpose.** An earlier blanket `git stash` reverted the *tracked*
> SQLite database to its committed snapshot on every deploy, silently discarding every inquiry
> received since the last commit. The stash pathspec list above contains only source-file
> extensions — `*.db` is not in it, so the database is never stashed. The database is also
> untracked (see [Database](#database)).

### Other entry points
| Command | Purpose |
|---------|---------|
| `./deploy.sh` | Full deploy: pull → build → restart → health-check |
| `./deploy-quick.sh` | Same flow, faster (no forced rebuild) |
| `./deploy-one-liner.sh` | One-liner for a fresh clone (clones the repo if missing) |
| `make deploy` | Runs `./deploy.sh` |
| `make test` | Read-only sanity check (compile + import the app) |
| `make backup` | Copies the live DB out of the container |
| `make certbot-issue` | Issues the Let's Encrypt certificate |
| `make logs` / `make ps` / `make down` | Day-to-day operations |

### Makefile paths [v2]
The Makefile uses `APP_DIR ?= $(HOME)/a2m-digital-solutions` and
`COMPOSE ?= docker compose -f docker-compose.prod.yml`, so it resolves to
`/home/ubuntu/a2m-digital-solutions` on the server. The absolute `/home/ubuntu/...` paths in this
document and the `~/...` paths in the Makefile refer to the same directory.

### GitHub Actions CI/CD — `.github/workflows/deploy.yml` [v2]
**Triggers:** push to `main`, or manual workflow dispatch.

**Pipeline stages:**
1. **Test** — compile the backend and assert that `/health`, `/api/admin/login` and `/api/ai/chat` exist
2. **Build** — build and push `a2m-backend` and `a2m-frontend` to GHCR
3. **Deploy** — SSH to Oracle, pull the images, run `docker compose up -d`

**Permissions required:** `contents: read` and `packages: write` (without `packages: write` the
GHCR push fails).

**GitHub Secrets:**
| Secret | Description |
|--------|-------------|
| `ORACLE_HOST` | Oracle instance public IP |
| `ORACLE_SSH_KEY` | Private SSH key (base64 encoded) |
| `ORACLE_USER` | SSH user (usually `ubuntu`) |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PASSWORD` | Gmail App Password |
| `TO_EMAIL` | `anantamisal@gmail.com` |
| `A2M_ADMIN_PASSWORD` | Admin password — must match `backend/.env` |
| `A2M_ADMIN_USERNAME` | Admin username (optional, defaults to `admin`) |
| `A2M_GROQ_API_KEY` | Optional Groq key (LLM + Whisper STT) |
| `A2M_NVIDIA_API_KEY` | Optional NVIDIA key (LLM only) |
| `A2M_COOKIE_SECURE` | `true` in production |

> ⚠️ **CI updates only the keys it manages.** The workflow indexes the existing `KEY=` lines in
> `backend/.env` and rewrites only those, skipping empty secrets. It will **not** clobber a
> hand-pasted `NVIDIA_API_KEY` or any other manually-added key. Do not replace this with a
> heredoc that rewrites the whole file.

---

## ⚙️ Configuration Management

### Environment Files

| File | Location | Committed? | Purpose |
|------|----------|------------|---------|
| `.env.example` | `backend/.env.example` | ✅ Yes | Template — **also carries the admin credentials**, because the deploy scripts bootstrap `.env` from it |
| `.env` | `backend/.env` | ❌ No (gitignored) | Production secrets |

> ⚠️ The deploy scripts create `backend/.env` from `backend/.env.example` when it is missing.
> A default `ADMIN_PASSWORD` in `.env.example` therefore becomes the live admin password.
> **Set a real password in `.env.example` before the first go-live**, or the site is publicly
> accessible with the default credentials.

### Environment Variables (`backend/.env`) — [v2]

```bash
# ---- App ----
ENVIRONMENT=production
DEBUG=false
APP_NAME="A2M Digital Solutions API"
APP_VERSION=1.0.0

# ---- Server ----
HOST=0.0.0.0
PORT=8000

# ---- CORS ----
CORS_ORIGINS=["https://a2mdigitalsolutions.com","https://www.a2mdigitalsolutions.com"]

# ---- Database (relative to the container WORKDIR /app) ----
DATABASE_URL=sqlite:///./data/inquiries.db

# ---- Email (Gmail SMTP) ----
EMAIL_PROVIDER=gmail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-gmail@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_USE_TLS=true
FROM_EMAIL=info@a2mdigitalsolutions.com
FROM_NAME="A2M Digital Solutions"
TO_EMAIL=anantamisal@gmail.com

# ---- Rate limiting ----
RATE_LIMIT=10

# ---- Admin authentication [NEW] ----
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<set-a-strong-password>
ADMIN_SESSION_HOURS=24
COOKIE_SECURE=true

# ---- API docs ----
ENABLE_API_DOCS=true
```

### New keys in v2 — what changed and why

| Key | Default | Purpose |
|-----|---------|---------|
| `ADMIN_USERNAME` | `admin` | Username for the admin console. The user is created at startup if missing. |
| `ADMIN_PASSWORD` | `admin123` | Password for the admin console. **Change before go-live.** If it changes later, the backend re-hashes and syncs it on the next restart. |
| `ADMIN_SESSION_HOURS` | `24` | Lifetime of the `admin_token` session cookie. |
| `COOKIE_SECURE` | `false` | Sets the `Secure` flag on the session cookie. **Must be `true` in production** — it requires HTTPS, which is why it is `false` for local `http://` development. |
| `ENABLE_API_DOCS` | `true` | Serves `/docs` and `/redoc`. This gates the docs — **`DEBUG` does not**. |

### Admin password handling
- Passwords are hashed with **PBKDF2-HMAC-SHA256**, 260,000 iterations, with a per-user random salt.
  Legacy unsalted SHA-256 hashes from earlier versions are still accepted on login and upgraded.
- The password is compared with `secrets.compare_digest` (constant time).
- The session token is stored server-side in the `admin_sessions` table and expires after
  `ADMIN_SESSION_HOURS`. Expired sessions are purged at startup.
- The browser receives the token only as an **httpOnly** cookie. It is never exposed to JavaScript,
  so it cannot be read by an XSS payload and never appears in `localStorage`.

### Critical: Gmail App Password
1. Enable 2FA on your Google Account
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the 16-character password (no spaces) in `SMTP_PASSWORD`

### CORS Origins (Production)
```bash
CORS_ORIGINS=["https://a2mdigitalsolutions.com","https://www.a2mdigitalsolutions.com"]
```
The admin console is served from the same origin as the API, so same-origin requests never depend
on CORS. The list only matters for local development and any separate frontend host.

---

## 🤖 AI Agent Configuration [NEW in v2]

The admin console has an **AI Coach** page: speak into the microphone and it replies out loud with
a corrected English sentence, a grammar tip and a spoken reply.

### Provider model — keyless by default

The AI agent is **provider-agnostic**. Each stage (speech-to-text, language model, text-to-speech)
walks its own chain of providers and falls back to the next one when the current provider is
unconfigured or fails. A single retired model id or a single rate-limited service can never take
the whole agent down.

```
STT : browser SpeechRecognition  -> Groq Whisper        -> NVIDIA
LLM : Pollinations (keyless)    -> Groq               -> NVIDIA Nemotron
TTS : Microsoft Edge TTS (keyless) -> NVIDIA          -> browser speechSynthesis
```

**Out of the box, with no API key at all, the agent can:**
- hold a conversation (LLM via Pollinations, keyless),
- speak the reply (TTS via Microsoft Edge voices, keyless),
- and understand you — either through the browser's own speech recognition, or through the text box.

### Environment keys

```bash
# ---- Provider chains (comma separated, tried left to right) ----
LLM_PROVIDER_ORDER=pollinations,groq,nvidia
STT_PROVIDER_ORDER=groq,nvidia
TTS_PROVIDER_ORDER=edge,nvidia

# ---- Pollinations: keyless LLM, no signup required ----
POLLINATIONS_BASE_URL=https://text.pollinations.ai/openai
POLLINATIONS_MODEL=openai-fast

# ---- Groq: free tier — ONE key covers both LLM and Whisper STT ----
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_API_KEY=
GROQ_LLM_MODEL=llama-3.3-70b-versatile
GROQ_STT_MODEL=whisper-large-v3-turbo

# ---- Microsoft Edge TTS: keyless speech synthesis ----
EDGE_TTS_VOICE=en-US-AriaNeural

# ---- NVIDIA NIM: optional, server-side only ----
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_STT_MODEL=nvidia/parakeet-ctc-0.6b-asr
NVIDIA_LLM_MODEL=nvidia/llama-3.1-nemotron-70b-instruct
NVIDIA_TTS_MODEL=nvidia/parakeet-tts-0.6b-v2
NVIDIA_TTS_VOICE=Magdellene
NVIDIA_TIMEOUT=60
```

> 🔒 **API keys live only in `backend/.env`.** They are read by the backend and are never sent to
> the browser. The frontend only ever calls `/api/ai/*`. No key may ever appear in `admin.html`,
> `index.html`, or any other committed file.

### Optional keys, in priority order

| Priority | Key | What it adds | Where to get it |
|----------|-----|--------------|-----------------|
| 1 | `GROQ_API_KEY` | Removes the Pollinations throttle **and** enables server-side Whisper STT | https://console.groq.com/keys (free) |
| 2 | `NVIDIA_API_KEY` | An extra LLM fallback | https://build.nvidia.com (free tier) |

### Known provider limitations

- **Pollinations anonymous tier is throttled to 1 reply every 45 seconds per IP.** The backend
  detects this (HTTP 402 `FREE_LIMIT`) and returns a helpful message telling the admin to add a
  free `GROQ_API_KEY`. This is the single biggest quality-of-life improvement available.
- **`nvidia/llama-3.1-nemotron-70b-instruct` is live. `meta/llama-3.3-70b-instruct` is dead**
  (end of life 2026-08-26, returns HTTP 410). The default in `config.py` is the live model.
- **NVIDIA's audio routes are not served.** `POST /v1/audio/speech` and `/v1/audio/transcriptions`
  return a plain-text 404, so NVIDIA cannot act as the TTS or STT provider. It is an LLM fallback
  only.
- `edge-tts` must be installed in the backend image — it is pinned in `backend/requirements.txt`.

### Verifying the agent on the server
```bash
# Login and keep the cookie
curl -c /tmp/a2m-cookies.txt -X POST http://127.0.0.1:8000/api/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}'

# Which providers are ready?
curl -b /tmp/a2m-cookies.txt http://127.0.0.1:8000/api/ai/status

# A full text round-trip
curl -b /tmp/a2m-cookies.txt -X POST http://127.0.0.1:8000/api/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"I go to office yesterday","history":[]}'
# -> {"corrected":"I went to the office yesterday.","reply":"...","tip":"...","model":"openai-fast","provider":"pollinations"}

# Speech output (raw audio/mpeg bytes)
curl -b /tmp/a2m-cookies.txt -X POST http://127.0.0.1:8000/api/ai/speak \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello from A2M","voice":"en-US-AriaNeural"}' \
  -o /tmp/a2m-speech.mp3
file /tmp/a2m-speech.mp3
```

### The microphone needs a secure context [NEW in v2]

`navigator.mediaDevices.getUserMedia()` is only available in a **secure context**. That means:

| Where the site is served | Microphone | Notes |
|--------------------------|-----------|-------|
| `https://a2mdigitalsolutions.com` | ✅ Works | This is the production setup |
| `http://localhost` | ✅ Works | `localhost` is treated as secure |
| `http://<the server's IP>` | ❌ Blocked | Browsers refuse `getUserMedia` on plain HTTP |

If the site is opened over plain HTTP from a remote host, the browser blocks the microphone. The
AI Coach page detects this and automatically falls back to the **browser's built-in speech
recognition**, and in every case the **text box remains available** as the guaranteed fallback. The
"Type a sentence" field always works, regardless of HTTPS, browser or permissions.

This is also why `COOKIE_SECURE=true` and HTTPS are required for production: the session cookie is
marked `Secure`, so a plain-HTTP admin login would not work at all.

---

## 🔒 SSL/TLS Certificates

### Certificate Details
- **Provider:** Let's Encrypt
- **Domains:** `a2mdigitalsolutions.com`, `www.a2mdigitalsolutions.com`
- **Storage:** `/home/ubuntu/a2m-digital-solutions/certbot/conf/` → mounted at `/etc/letsencrypt`
- **Expiry:** 90 days (auto-renewal)

### The chicken-and-egg problem [v2]

The frontend container's nginx config points at
`/etc/letsencrypt/live/a2mdigitalsolutions.com/fullchain.pem`. On a **first** deploy that file does
not exist yet, so nginx would fail to start.

`docker-entrypoint.sh` breaks this cycle: when the real certificate is absent it **mints a
self-signed certificate** at the expected path so nginx can start, and prints the exact certbot
command to run. Issue the real certificate once, then restart the frontend.

### Issuing the real certificate [v2]
```bash
cd /home/ubuntu/a2m-digital-solutions

# Option A - via the Makefile target
make certbot-issue

# Option B - manually, using the certbot compose service
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  --email anantamisal@gmail.com \
  --agree-tos --no-eff-email \
  -d a2mdigitalsolutions.com -d www.a2mdigitalsolutions.com

# Then restart nginx so it picks up the real certificate
docker compose -f docker-compose.prod.yml restart frontend
```

**Prerequisites:** the domain must already resolve to `140.238.242.134`, and port 80 must be open
(the ACME HTTP-01 challenge runs over plain HTTP).

### Auto-Renewal [v2]
Renewal is handled by the **`certbot` compose service**, which runs `certbot renew --webroot` every
12 hours. No root crontab is required any more.

```bash
# Check that the service is running
docker compose -f docker-compose.prod.yml ps certbot

# See renewal logs
docker compose -f docker-compose.prod.yml logs certbot

# Force a renewal dry-run
docker compose -f docker-compose.prod.yml run --rm certbot renew --dry-run
```

### Certificate Verification
```bash
# Check expiry
openssl x509 -in /home/ubuntu/a2m-digital-solutions/certbot/conf/live/a2mdigitalsolutions.com/fullchain.pem \
  -text -noout | grep "Not After"

# Test from outside
echo | openssl s_client -connect a2mdigitalsolutions.com:443 2>/dev/null | openssl x509 -noout -dates
```

---

## 📧 Email Configuration

### Gmail SMTP (Current)
| Setting | Value |
|---------|-------|
| Provider | Gmail SMTP |
| Host | `smtp.gmail.com` |
| Port | `587` (STARTTLS) |
| Auth | Gmail App Password |

### Email Flow
```
User submits form → Backend validates → Row stored in SQLite → Async email sent → Response returned
                                          │                    │
                                          │                    └──► Gmail SMTP (Port 587, STARTTLS)
                                          └──► inquiry row is written BEFORE the email is attempted
```
The email is sent in a background task, so a slow or failing SMTP server never blocks the user's
form submission. **A failed email does not lose the inquiry** — the row is already committed.

### Email Templates
- **HTML:** Professional gradient header, styled tables, responsive
- **Plain Text:** Fallback for text-only clients
- **Reply-To:** Set to the user's email for direct reply

### Troubleshooting Email
```bash
# Check backend logs for email status
docker compose -f docker-compose.prod.yml logs backend | grep -i email

# Expected success:
# "Email sent successfully via gmail SMTP"

# Common issues:
# - "SMTP credentials not configured" → Check .env
# - "SSL: WRONG_VERSION_NUMBER" → Port 587 needs STARTTLS (not implicit TLS)
# - "Authentication failed" → Wrong app password
```

---

## 🗄️ Database

### Database: SQLite [v2]
- **File on the server:** `/home/ubuntu/a2m-digital-solutions/backend/data/inquiries.db`
- **Path inside the container:** `/app/data/inquiries.db`
- **Mount:** `./backend/data:/app/data` (a bind mount, so the data survives image rebuilds)
- **ORM:** SQLAlchemy 2.0
- **Tables:** `inquiries`, `visitor_counts`, `admin_users`, `admin_sessions`

> ⚠️ **The database must not be tracked by git.** It is untracked (see below) and the deploy scripts
> stash only source-file extensions, so it is never reverted or overwritten by a deploy.

### Untracking the database and bytecode [v2]
```bash
# The .db file and the .pyc files must not be in git
git rm --cached backend/inquiries.db
git rm --cached backend/__pycache__/*.pyc

# Confirm nothing is tracked
git ls-files backend/ | grep -E "\.db$|\.pyc$"   # must print nothing
```

> ⚠️ **`git rm --cached` with a glob aborts the whole command** if any matched path is untracked.
> List the tracked paths explicitly instead of using `*.pyc`.
>
> ⚠️ These deletions are **staged**. They only reach the server once the change is **committed**.
> Until then a fresh clone still tracks the database — although the scoped stash already protects
> it in the meantime.

### Schema
```sql
-- Inquiries
CREATE TABLE inquiries (
    id INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    service VARCHAR(100) NOT NULL,
    timeline VARCHAR(50),
    message TEXT NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    status VARCHAR(20) DEFAULT 'new',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Visitor Counts (one row per day)
CREATE TABLE visitor_counts (
    id INTEGER PRIMARY KEY,
    date DATE UNIQUE NOT NULL,
    count INTEGER DEFAULT 0,
    unique_visitors INTEGER DEFAULT 0
);

-- Admin Users
CREATE TABLE admin_users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login DATETIME
);

-- Admin Sessions (server-side session tokens)
CREATE TABLE admin_sessions (
    id INTEGER PRIMARY KEY,
    token VARCHAR(128) UNIQUE NOT NULL,
    admin_id INTEGER NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Default Admin User [v2]
| Field | Value |
|-------|-------|
| Username | `admin` (`ADMIN_USERNAME`) |
| Password | `ADMIN_PASSWORD` — **change immediately**, the default is `admin123` |

The admin user is created automatically at startup if it does not exist, and the password is
re-synced from `ADMIN_PASSWORD` on every restart if it has changed.

### Backup [v2]
```bash
# Manual backup
mkdir -p /home/ubuntu/backups
docker cp a2m-backend:/app/data/inquiries.db /home/ubuntu/backups/inquiries-$(date +%Y%m%d).db

# Or: make backup

# Automated backup (add to the ubuntu crontab)
0 2 * * * docker cp a2m-backend:/app/data/inquiries.db /home/ubuntu/backups/inquiries-$(date +\%Y\%m\%d).db
```

---

## 🔐 Admin Dashboard & AI Coach

### Access
- **URL:** `https://a2mdigitalsolutions.com/admin.html`
- **Username:** `ADMIN_USERNAME` (default `admin`)
- **Password:** `ADMIN_PASSWORD` (**change immediately**, default `admin123`)

### Pages [v2]

| Page | Features |
|------|----------|
| **Dashboard** | Total / new / contacted / closed inquiry counts, visitor stats, the five most recent inquiries |
| **Inquiries** | Searchable, filterable, paginated table (20 per page) with an inline status dropdown |
| **Visitors** | Total visits, today's visits, unique visitors, and how tracking works |
| **AI Coach** | Voice conversation with English correction, grammar tip and a spoken reply |

### How the login works [v2]
1. `POST /api/admin/login` with `{"username": ..., "password": ...}` as JSON.
2. The server verifies the PBKDF2 hash and creates a server-side session.
3. The browser receives the token as an **httpOnly** cookie (`admin_token`, `SameSite=Lax`,
   `Secure` when `COOKIE_SECURE=true`).
4. **The token is never stored in JavaScript.** Every subsequent request is sent with
   `credentials: 'include'` so the browser attaches the cookie automatically.
5. On page load the console calls `GET /api/admin/stats`: a **200 means the session is still valid**
   and the dashboard opens; a **401 means it is not** and the login screen is shown.
6. Any API call that returns 401 (an expired session) bounces the UI back to the login screen.

### Verified endpoint contract [v2]

This table was checked against the live `/openapi.json`. **Use these exact paths.**

| Method | Path | Auth | Body / Query | Returns |
|--------|------|------|--------------|---------|
| POST | `/api/admin/login` | — | JSON `{username, password}` | `{access_token, token_type}` + httpOnly `admin_token` cookie |
| POST | `/api/admin/logout` | — | — | `{message}` |
| GET | `/api/admin/stats` | admin | — | flat `total, new, contacted, closed, total_visits, today_visits, unique_visitors` plus nested `inquiries{}` / `visitors{}` and `admin` |
| GET | `/api/inquiries` | admin | `?page=N&per_page=20&status_filter=` | `{inquiries[], total, page, per_page, total_pages}` |
| PATCH | `/api/inquiries/{id}/status` | admin | JSON `{status}` | the updated inquiry |
| GET | `/api/visitors` | public | — | `{total_visits, today_visits, unique_visitors}` |
| POST | `/api/visitors/track` | public | `{}` | the same visitor stats |
| GET | `/api/ai/status` | admin | — | `{configured, providers{llm,stt,tts}, browser_fallback, models, base_url}` |
| POST | `/api/ai/transcribe` | admin | multipart, field name **`file`** | `{text}` |
| POST | `/api/ai/chat` | admin | JSON **`{text, history}`** | `{corrected, reply, tip, model, provider}` |
| POST | `/api/ai/speak` | admin | JSON `{text, voice}` | **raw `audio/mpeg` bytes** |
| GET | `/health` | — | — | `{status, app_name, version, environment}` |

> ⚠️ **Two route names that are easy to get wrong:**
>
> 1. **There is no `/api/admin/inquiries`.** The paginated list is served by
>    **`GET /api/inquiries`** (query parameter **`status_filter`**). There is also a legacy alias
>    **`GET /admin/inquiries`** (query parameter **`status`**) — note the different parameter name.
> 2. **There is no `/admin/inquiries/{id}/status`.** The status update is
>    **`PATCH /api/inquiries/{id}/status`**. The `/admin/` prefix only covers `/admin/login`,
>    `/admin/logout`, `/admin/stats` and `/admin/inquiries`.

> **Error bodies.** The backend returns `{"detail": "..."}` for ordinary errors and
> `{"detail": [{"msg": "...", "loc": [...], "type": "..."}]}` for 422 validation errors. The frontend
> handles both shapes.

### AI Coach request/response shapes [v2]
```bash
# Transcription: the multipart field MUST be named "file"
curl -b cookies.txt -X POST http://127.0.0.1:8000/api/ai/transcribe \
  -F "file=@speech.webm"

# Chat: the field is "text", NOT "message"
curl -b cookies.txt -X POST http://127.0.0.1:8000/api/ai/chat \
  -H 'Content-Type: application/json' \
  -d '{"text":"I go to office yesterday","history":[]}'

# Speak: returns raw audio bytes, not JSON
curl -b cookies.txt -X POST http://127.0.0.1:8000/api/ai/speak \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello","voice":"en-US-AriaNeural"}' -o speech.mp3
```

### Admin console behaviour notes [v2]
- **The dashboard is a static file.** nginx serves `admin.html` directly; only its `/api/*` calls
  are proxied. This is why the visitor counter cannot be done with request middleware (see below).
- **XSS-safe rendering.** Inquiry names, emails and messages are inserted with `textContent`, never
  by interpolating into `innerHTML`. A submission containing `<script>alert(1)</script>` is
  displayed as literal text and does not execute.
- **The AI agent is admin-only.** It is not reachable from the public site. (Keeping it inside the
  admin area is the safer default.)
- **Mic states** run `idle → recording → transcribing → thinking → speaking`. If the server TTS
  fails or autoplay is blocked, the console falls back to the browser's `speechSynthesis`.

---

## 📊 Visitor Tracking [REWRITTEN in v2]

### How it works now

The old implementation counted every request the backend happened to see. **That was measuring the
wrong thing.** In production, nginx serves `index.html` and `admin.html` as static files, so the
backend never sees the page request itself — only `/api/*` traffic. The visitor count therefore
tracked API calls, and `unique_visitors` was permanently `0`.

The counter now works by an **explicit tracking call**:

```
Browser loads index.html
        │
        └──► fetch('/api/visitors/track', {method: 'POST'})   ← one call, on page load
                      │
                      ▼
             Backend reads the client IP
             (X-Forwarded-For first, then request.client.host)
                      │
                      ├──► today's row: count += 1
                      └──► unique_visitors += 1 only the first time
                          this IP is seen today (per-day in-memory set)
```

The tracking call is wrapped in a `.catch()`, so **a failing counter never breaks the public page**.

### The middleware no longer counts
```python
# backend/main.py
@app.middleware("http")
async def track_visitors(request: Request, call_next):
    """The counter is incremented by the frontend calling POST /api/visitors/track
    on page load, not here: in production nginx serves the HTML directly, so the
    backend never sees the page request itself."""
    return await call_next(request)
```

### Metrics Tracked
| Metric | Description |
|--------|-------------|
| `total_visits` | All page views (all time) |
| `today_visits` | Page views recorded since midnight |
| `unique_visitors` | Distinct addresses counted once per day |

The per-day IP set is kept **in memory on purpose** — it only feeds a daily counter, and resetting
it when the backend restarts is harmless. It is capped at 20,000 addresses.

### Endpoints
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/visitors/track` | public | Record one page view, return the current stats |
| GET | `/api/visitors` | public | Read the current stats without recording a visit |

---

## 🔧 Monitoring & Maintenance

### Health Checks [v2]
```bash
# Backend health (proxied through nginx)
curl https://a2mdigitalsolutions.com/health

# Backend health from inside the container
docker compose -f docker-compose.prod.yml exec backend \
  curl -f http://127.0.0.1:8000/health

# Frontend
curl -I https://a2mdigitalsolutions.com

# API docs (gated by ENABLE_API_DOCS, not DEBUG)
curl -I https://a2mdigitalsolutions.com/docs
curl https://a2mdigitalsolutions.com/openapi.json | head
```

> The health endpoint is **`/health`**, not `/api/health`. There is no `/api/health` route.

### Logs
```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend
docker compose -f docker-compose.prod.yml logs -f certbot

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail=100 backend
```

### Service Status
```bash
# Check container status
docker compose -f docker-compose.prod.yml ps

# Container resource usage
docker stats --no-stream
```

### On startup the backend prints its readiness [v2]
```
🚀 A2M Digital Solutions API v1.0.0 started
📧 Email provider: gmail
🗄️  Database: sqlite:///./data/inquiries.db
🤖 AI Agent: LLM=pollinations TTS=edge
🔑 Groq: configured (optional provider)
```
The `AI Agent` line tells you immediately which providers are live. If it says `LLM=none`, the agent
will not answer — check `backend/.env` and the `GROQ_API_KEY` / `NVIDIA_API_KEY` values.

### Cron Jobs
```bash
# View crontabs
crontab -l          # User crontab (backups)

# Cron service status
sudo systemctl status cron
```

> Certificate renewal no longer needs a cron entry — the `certbot` compose service handles it.

---

## 🔧 Troubleshooting Guide

### Common Issues & Fixes

| Issue | Symptoms | Solution |
|-------|----------|----------|
| **404 on `/api/*`** | Nginx proxy not forwarding | Check `proxy_pass http://a2m_backend;` — **no trailing slash, no URI part** |
| **`/admin/*` returns 404** | The `/admin/` location rule is missing or has a trailing slash | Restore `location /admin/ { proxy_pass http://a2m_backend; }` |
| **502 Bad Gateway** | Backend not running or not healthy | `docker compose -f docker-compose.prod.yml logs backend`; check `compose ps` |
| **SSL Certificate Error** | Cert expired or missing | The entrypoint mints a self-signed cert as a placeholder — issue the real one, then `compose restart frontend` |
| **`docker-compose: command not found`** | Compose v1 is not installed | Use `docker compose` (v2). If the plugin is missing: `sudo apt-get install docker-compose-v2` |
| **Login succeeds but every page is empty** | The session cookie was not stored | Check `COOKIE_SECURE=true` while serving over plain HTTP — the browser silently drops a `Secure` cookie |
| **CORS Error** | Frontend can't call the API | Check `CORS_ORIGINS` in `.env` |
| **Email Not Sending** | No "Email sent successfully" in the logs | Verify the Gmail App Password, check the spam folder. The inquiry row is still stored either way |
| **422 Unprocessable Entity** | Validation error | The body carries `detail` as an array of `{msg, loc, type}` objects — read `msg` |
| **AI Coach replies "no provider could answer"** | Every provider in the chain failed | Check `LLM_PROVIDER_ORDER` in `.env` and the backend startup log line |
| **AI Coach says "Pollinations free tier allows 1 reply every 45 seconds"** | Anonymous tier throttle | Add a free `GROQ_API_KEY` |
| **Microphone does nothing** | `getUserMedia` blocked | The page must be served over **HTTPS** (or `localhost`). The text box always works |
| **Visitor counter stuck at 0** | The tracking call is not firing | Check the browser console for `POST /api/visitors/track`; confirm nginx serves `index.html` statically |
| **Port 80/443 in Use** | Host nginx running | `sudo systemctl stop nginx && sudo systemctl disable nginx` |
| **Compose "ContainerConfig" error** | Stale containers | `docker compose -f docker-compose.prod.yml down && docker rm -f a2m-frontend a2m-backend a2m-certbot` |

### Debug Commands
```bash
# Backend logs
docker compose -f docker-compose.prod.yml logs -f backend

# Test the backend from inside its own container
docker compose -f docker-compose.prod.yml exec backend curl -s http://127.0.0.1:8000/health

# Test the API through nginx
curl -s https://a2mdigitalsolutions.com/health
curl -s https://a2mdigitalsolutions.com/openapi.json | python3 -m json.tool | head -40

# Check the nginx config in the container
docker exec a2m-frontend cat /etc/nginx/conf.d/default.conf

# Validate the compose file before deploying
docker compose -f docker-compose.prod.yml config

# Check the database
docker exec a2m-backend sqlite3 /app/data/inquiries.db ".tables"
docker exec a2m-backend sqlite3 /app/data/inquiries.db "SELECT id,name,status,created_at FROM inquiries ORDER BY id DESC LIMIT 10;"
```

### DNS Issues
```bash
# Verify DNS resolution
dig a2mdigitalsolutions.com +short
dig www.a2mdigitalsolutions.com +short

# Should return: 140.238.242.134
# If showing Cloudflare IPs → Proxy is ON (should be DNS Only for cert issuance)
```

---

## 🔄 Rollback Procedure

### Quick Rollback (Code Only)
```bash
cd /home/ubuntu/a2m-digital-solutions
git log --oneline -5
git revert HEAD            # or: git reset --hard <previous-commit-hash>

# Rebuild and deploy
./deploy.sh
```

> The scoped stash never touches `*.db`, so rolling back the code does not roll back the data.

### Full Rollback (Including Database)
```bash
# 1. Stop services
docker compose -f docker-compose.prod.yml down

# 2. Restore the database from a backup
docker cp /home/ubuntu/backups/inquiries-20261110.db a2m-backend:/app/data/inquiries.db

# 3. Restore the code
git checkout <previous-working-commit>

# 4. Rebuild and start
./deploy.sh
```

### Emergency Rollback (Docker Images)
```bash
docker tag a2m-backend:previous a2m-backend:latest
docker tag a2m-frontend:previous a2m-frontend:latest
docker compose -f docker-compose.prod.yml up -d
```

---

## 🔒 Security Checklist

### Pre-Deployment
- [ ] `.env` not committed to git (it is gitignored)
- [ ] Gmail App Password used (not the regular account password)
- [ ] **Admin password changed from the default** in `backend/.env` **and** in `backend/.env.example`
      (the deploy scripts bootstrap `.env` from `.env.example`)
- [ ] `COOKIE_SECURE=true` in production
- [ ] SSH key-based auth only (password auth disabled)
- [ ] Firewall: only ports 22, 80, 443 open — **8000 must stay closed** (the backend has no host port)
- [ ] Cloudflare proxy enabled (after the SSL cert is issued)
- [ ] Rate limiting enabled (`RATE_LIMIT=10` requests/minute per IP)

### Post-Deployment
- [ ] SSL certificate valid (check expiry) and the **real** cert is in place, not the self-signed placeholder
- [ ] HTTPS redirect working (HTTP → HTTPS)
- [ ] `https://a2mdigitalsolutions.com/health` returns `"status": "healthy"`
- [ ] `https://a2mdigitalsolutions.com/admin.html` loads and the login works
- [ ] Admin password changed
- [ ] The AI Coach works (check the backend startup line: `LLM=… TTS=…`)
- [ ] The microphone works over HTTPS
- [ ] Backup schedule configured
- [ ] `backend/inquiries.db` is **not** tracked by git
- [ ] Monitoring alerts configured

### Regular Maintenance
| Frequency | Task |
|-----------|------|
| Daily | Certificate renewal (automatic, via the certbot service) |
| Weekly | Check logs for errors; confirm the DB backup exists |
| Monthly | Update system packages, review logs |
| Quarterly | Rotate SSH keys, review access |
| Annually | Renew the domain, review security |

---

## 📞 Emergency Contacts & Resources

| Resource | URL/Contact |
|----------|-------------|
| Oracle Cloud Console | https://cloud.oracle.com |
| Cloudflare Dashboard | https://dash.cloudflare.com |
| GitHub Repo | https://github.com/anantamisal/a2m-digital-solutions |
| Let's Encrypt Status | https://letsencrypt.org/status/ |
| Gmail App Passwords | https://myaccount.google.com/apppasswords |
| Groq API keys (optional AI) | https://console.groq.com/keys |
| NVIDIA API catalog (optional AI) | https://build.nvidia.com |

---

## 📝 Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-11-10 | 2.0 | Compose v2 throughout; corrected nginx rules incl. `location /admin/`; documented the real endpoint contract; documented the AI provider chains and the mic secure-context requirement; new admin-auth env keys; visitor tracking moved to `POST /api/visitors/track`; certbot compose service replaces the cron job; admin console rewritten |
| 2026-11-07 | 1.0 | Initial deployment documentation |

---

**Document Owner:** Ananta Misal
**Last Review:** 2026-11-10
**Next Review:** 2027-02-10

---

*This document is the single source of truth for A2M Digital Solutions deployment. Update it whenever infrastructure or deployment process changes.*

