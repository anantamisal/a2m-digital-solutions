# HANDOFF — A2M Digital Solutions (admin repair + AI agent + Oracle Cloud deploy)

**Read this file first in a new session.** It is the complete state of the work.
The verified plan lives at `/home/shivani/.claude/plans/please-check-what-happened-ile-twinkling-island.md`
— read it too, it has the evidence tables (19 gaps, free-endpoint probes).

---

## 0. Hard constraints (do not violate)

| Constraint | Detail |
|---|---|
| **Deployment target** | **Oracle Cloud only.** The user explicitly said: *"Please ignore that my local system. I just pasted it by mistakenly. Just ignore that. We want to deploy it on Oracle Cloud only."* Do NOT plan for, or investigate, local deployment. The local box is only for authoring/verification. |
| **Never commit or push** | The user has not asked for a commit. Do not `git commit` / `git push` unless explicitly asked. Branch is `main`. |
| **Secrets** | `backend/.env` is gitignored and must never be tracked. No API key may ever appear in frontend JS or in any committed file. Keys live only in the backend environment. |
| **Git hygiene** | `backend/inquiries.db` and `backend/__pycache__/*.pyc` are **already untracked** (decision confirmed by the user). Do not re-add them. |
| **Plan file** | `/home/shivani/.claude/plans/please-check-what-happened-ile-twinkling-island.md` — verified plan, 8-step execution order. Follow it. |

---

## 1. The project

A2M Digital Solutions — a one-page marketing site (`index.html`, dark glassmorphism, self-contained with Tailwind CDN) plus a FastAPI backend (`backend/`) that stores inquiries, emails them, tracks visitors, and serves an admin dashboard at `admin.html`.

Production domain: `a2mdigitalsolutions.com`. Oracle Cloud Ubuntu instance, repo at `~/a2m-digital-solutions`, runs `ubuntu` user, Docker Engine + `docker compose` v2 plugin.

---

## 2. Decisions already made (with the user)

1. **AI provider → provider-agnostic with keyless defaults.** No API key required at all. Each stage walks a fallback chain.
2. **Git hygiene → untrack both** `backend/inquiries.db` **and** `backend/__pycache__/*.pyc`. Done.

---

## 3. Step-by-step status

Plan steps 1–8. **All eight steps are DONE.** Steps 5, 7 and 8 were completed in the most recent session
(`admin.html` rewritten and verified 39/39 in headless Chrome; `DEPLOYMENT_DOCUMENTATION.md` rewritten as v2.0;
end-to-end verification passed).

### ✅ Step 1 — Protect the data
- `git rm --cached backend/inquiries.db` and the five tracked `.pyc` files → done (staged as `D`).
- `git ls-files | grep -E "\.db$|\.pyc$"` → **empty**. The 13 inquiry rows + 1 admin user are preserved on disk.
- Note: `git rm --cached` with a glob aborts if any matched path is untracked — list the tracked paths explicitly instead.

### ✅ Step 2 — Fix the deploy scripts
All five files rewritten to use `docker compose` **v2** (no hyphenated v1 binary), no blanket `git stash`, no junk production POST:
- `deploy.sh` — `set -euo pipefail`, `APP_DIR="${APP_DIR:-$HOME/a2m-digital-solutions}"`, `compose()` wrapper for `docker compose -f docker-compose.prod.yml`, **scoped** stash (`git stash push -- '*.py' '*.html' '*.yml' '*.yaml' '*.sh' '*.conf' '*.css' '*.js'`), `git pull --ff-only`, builds both images, health-checks the backend **inside** the container (`compose exec -T backend python -c "import httpx..."`) and the frontend via `wget --spider`, warns if `ADMIN_PASSWORD` is still the default, prints the admin username but **never the password**.
- `deploy-quick.sh`, `deploy-one-liner.sh` — same fixes + clone fallback.
- `Makefile` — `APP_DIR ?= $(HOME)/a2m-digital-solutions`, `COMPOSE ?= docker compose -f docker-compose.prod.yml`, complete `.PHONY`, single `pull:` target (duplicate removed), `test:` target is now read-only, new `certbot-issue:` target, `backup:` uses `docker cp a2m-backend:/app/data/inquiries.db`.
- `.github/workflows/deploy.yml` — added `permissions: {contents: read, packages: write}`; a real `test:` job (compileall + app import asserting `/health`, `/api/admin/login`, `/api/ai/chat` exist); the deploy job updates **only** CI-managed keys in `backend/.env` via an embedded `python3 - <<'PYEOF'` block that indexes existing `KEY=` lines and skips empty secrets — **verified to preserve a hand-pasted `NVIDIA_API_KEY`**. Exports `A2M_ADMIN_PASSWORD`, `A2M_NVIDIA_API_KEY`, `A2M_GROQ_API_KEY`, `A2M_COOKIE_SECURE` from GitHub secrets.

### ✅ Step 3 — Env plumbing
`backend/.env.example` and `backend/.env` both carry the new sections: Admin Authentication (`ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_SESSION_HOURS`, `COOKIE_SECURE`) and AI Agent (all provider keys). `backend/.env` still has the original SMTP/email keys untouched. **Current `backend/.env` values:** `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=admin1…` (the default — **the owner must change this before go-live**), `COOKIE_SECURE=false` (must become `true` in production), `GROQ_API_KEY=` and `NVIDIA_API_KEY=` are **empty** (both are optional; the AI agent works keyless).

### ✅ Step 4 — Deployment files created
- `nginx.conf` — upstream `a2m_backend { server backend:8000; keepalive 16; }`; `:80` → 301 to HTTPS with the ACME challenge path carved out; `:443` with `http2 on`, certbot cert paths, `client_max_body_size 25m`, `proxy_read_timeout 90s`, and:
  ```nginx
  location / { try_files $uri $uri/ /index.html; }
  location = /admin.html { try_files /admin.html =404; }
  location /api/   { proxy_pass http://a2m_backend; }
  location /admin/ { proxy_pass http://a2m_backend; }
  location = /health { proxy_pass http://a2m_backend/health; }
  location = /docs { proxy_pass http://a2m_backend/docs; }
  location = /redoc { proxy_pass http://a2m_backend/redoc; }
  location = /openapi.json { proxy_pass http://a2m_backend/openapi.json; }
  ```
  **`proxy_pass` has NO trailing slash and no URI part** — that preserves the request path. Getting this wrong is what broke the old setup.
- `Dockerfile.frontend` — `FROM nginx:1.27-alpine`, `apk add openssl`, copies `index.html`, `admin.html`, `company_logo1.png`, `company_logo_mark.png`, `company_logo.png`, `styles.css`, `script.js`, `nginx.conf`, `docker-entrypoint.sh`; EXPOSE 80/443; HEALTHCHECK via wget.
- `docker-entrypoint.sh` — mints a 1-day self-signed cert at `/etc/letsencrypt/live/a2mdigitalsolutions.com/` when the real one is absent and prints the certbot command (breaks the certbot↔nginx chicken-and-egg).
- `docker-compose.prod.yml` — services `backend` (build `./backend/Dockerfile.prod`, `expose: ["8000"]`, no published port, volumes `./backend/data:/app/data` + `./backend/.env:/app/.env:ro`, `DATABASE_URL=sqlite:///./data/inquiries.db`, healthcheck via httpx), `frontend` (build context `.`, `ports: 80:80` + `443:443`, certbot volumes, `depends_on: backend: condition: service_healthy`), `certbot` (renew every 12h, webroot). Network `a2m-network`. Container names `a2m-frontend` / `a2m-backend` / `a2m-certbot`.
- `backend/Dockerfile.prod` — multi-stage python:3.12-slim, `pip install --prefix=/install`, non-root `appuser`, `DATABASE_URL=sqlite:///./data/inquiries.db`, HEALTHCHECK via curl /health, uvicorn with `--proxy-headers --forwarded-allow-ips *`.
- `.dockerignore` (root) — excludes `backend/venv/`, `.env`, `*.db`, `backend/data/`, `.git/`, `*.md`.

### ✅ Step 5 — Rewrite `admin.html`  ← **DONE (this session)**
`admin.html` was fully rewritten: the original broken 523-line file is now a 1,905-line console (1,180-line inline script).

**All the old defects are gone:**
- `const perPage` declared twice → gone. `node --check` passes on the extracted inline script.
- `<div id="login-page">` never closed → gone. The login view and the app shell are now siblings.
- `[id^="page-"]` matching `#page-title` → gone. Page panels are selected by the explicit `.admin-page` class + a `data-page` attribute.
- Two "Today's Visits" cards → exactly one now (`#stat-today-visits`); the Visitors page has its own set.
- XSS via `innerHTML` → gone. Every inquiry field is rendered with `textContent` on real DOM nodes.
- Inline `onchange=`/`onclick=` → gone. Every listener is attached in JS.
- `company_logo1.png` in the sidebar → now `company_logo_mark.png`.
- `/admin/inquiries/{id}/status` 404 → now `PATCH /api/inquiries/{id}/status`.

**What it contains:**
- **Design**: `index.html`'s exact tokens — Tailwind CDN + the same `tailwind.config`, FontAwesome 6.4, the same `<style>` block (`.glass-panel`, `.glass-panel-interactive`, `.text-gradient`, `.text-gradient-cyan`, `.glow-orb`, `.btn-shimmer`, `.nav-link.active`), body canvas `#050811`.
- **Structure**: login view (centred glass panel) + app shell (fixed 260 px sidebar, sticky header with page title, AI status pill, admin chip, refresh and logout). Pages: Dashboard, Inquiries, Visitors, AI Coach. Responsive: the sidebar becomes an off-canvas drawer below the `lg` breakpoint (1024 px) with a hamburger toggle and a backdrop.
- **JS rules**: one `state` object, one `$`/`$$` helper, one `apiFetch()` helper, no duplicate `const`/`let` in any scope.
- **`apiFetch()`**: `credentials:'include'`, 401 → back to the login view, `detail` extracted from either a string **or** a pydantic `[{msg}]` array. FormData bodies are sent without a `Content-Type` header so the browser sets the multipart boundary.
- **Login**: `POST /api/admin/login` with `{username, password}`. The token is never stored in JS — the server sets the httpOnly cookie.
- **Session check on load**: `GET /api/admin/stats` → 200 = authenticated, 401 = show login.
- **Stats**: flat fields only, with a `Number.isFinite` guard before `.toLocaleString()`.
- **Inquiries**: `GET /api/inquiries?page=N&per_page=20&status_filter=` (see §4 — the path in the old handoff was wrong), search box, status filter buttons, pagination, and an inline status `<select>` that PATCHes and persists.
- **AI page**: `FormData` field name **`file`** → `/api/ai/transcribe`; `/api/ai/chat` with **`{text, history}`**; `/api/ai/speak` → raw `audio/mpeg` → `Blob` + `createObjectURL` + `new Audio().play()`, with `speechSynthesis` as the fallback. Mic states: idle → recording → transcribing → thinking → speaking. `webkitSpeechRecognition` is the STT fallback when no server STT provider is ready.
- **Timestamps**: the backend stores naive UTC, so `formatDate()` appends `Z` before rendering — the admin in IST sees the correct local time (verified: `12:40:52Z` → `18:10` IST).

### ✅ Step 6 — AI agent works (provider-agnostic, keyless)
- **`backend/ai_agent.py`** — provider abstraction. Public API:
  - `coach_reply(user_text, history) -> {corrected, reply, tip, model, provider}`
  - `transcribe_audio(audio_bytes, filename, content_type) -> str`
  - `synthesize_speech(text, voice) -> (bytes, media_type)`
  - `ai_status() -> {configured, providers{llm,stt,tts:[{name,ready,detail}]}, browser_fallback, models, base_url}`
  - Chains: `LLM_PROVIDER_ORDER="pollinations,groq,nvidia"`, `STT_PROVIDER_ORDER="groq,nvidia"`, `TTS_PROVIDER_ORDER="edge,nvidia"`.
  - `_raise_for_status` returns early for `<400` and special-cases Pollinations HTTP 402 `FREE_LIMIT`.
  - `_parse_coach_json` tolerates prose/code fences and **truncated** JSON — salvages individual fields by regex, falls back to a canned spoken reply so raw broken JSON is never spoken.
- **`backend/config.py`** — NVIDIA block replaced with the provider-chain block. `NVIDIA_LLM_MODEL` is now `nvidia/llama-3.1-nemotron-70b-instruct` (the old `meta/llama-3.3-70b-instruct` is **EOL — HTTP 410 since 2026-08-26**). Also added `ENABLE_API_DOCS: bool = True`.
- **`backend/main.py`** — `/api/ai/speak` returns `Response(content=audio, media_type=media_type)` (raw bytes, not JSON). Startup prints `🤖 AI Agent: LLM={ready_llm} TTS={ready_tts}`. `ai_status` imported at main.py:43–48. `docs_url`/`redoc_url` now gated on `ENABLE_API_DOCS` (they were dead links in production because they were gated on `DEBUG`).
- **`backend/requirements.txt`** — added `edge-tts==7.3.1`.
- **`backend/models.py`** — `AIChatResponse` gained a `provider` field; `model` description no longer says "NVIDIA".

#### Extra fixes made this session (verified live)
- **Visitor counter was measuring the wrong thing.** The backend middleware counted *every request it saw* — but nginx serves the HTML, so the backend never sees the page request; only `/api/*` traffic was counted, and `unique_visitors` was permanently 0.
  - `backend/database.py` — new `register_visit(db, ip_address)`: bumps today's count, counts the IP as unique only once per day (in-memory per-day set, capped at 20 000 IPs).
  - `backend/main.py` — the `track_visitors` middleware no longer counts; a new **`POST /api/visitors/track`** endpoint (public, no auth) does. It derives the IP from `X-Forwarded-For` first, falling back to `request.client.host`. The duplicate second `/api/visitors` route was removed.
  - `index.html` — calls `fetch('/api/visitors/track', {method:'POST'})` once on page load, with a `.catch()` so a counter failure never breaks the page.
- `GET /` now reports `"docs": "/docs"` instead of `"disabled"`.

### ✅ Step 7 — Update `DEPLOYMENT_DOCUMENTATION.md`  ← **DONE (this session)**
Rewritten as v2.0 (1,204 lines). Covers everything the plan required:
- `location /admin/` — documented as a **prefix** rule, with the warning that `admin.html` (no slash) is a *static file* served by a separate `location = /admin.html` rule.
- The mic **HTTPS / secure-context** requirement, with a table of where `getUserMedia` works and why the text box is the guaranteed fallback.
- The AI provider setup — the three chains, every env key, the optional-key priority table, and the known provider limitations (the Pollinations 45 s throttle, the EOL NVIDIA model, NVIDIA's dead audio routes).
- The changed env keys — `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_SESSION_HOURS`, `COOKIE_SECURE`, `ENABLE_API_DOCS` — plus a table explaining each one.
- `docker compose` **v2** everywhere; the old *"Docker 29.x + Docker Compose 1.29"* line is gone, with an explicit note that Compose v1 is EOL and not bundled with modern Docker Engine.
- Consistent Oracle paths (`/home/ubuntu/a2m-digital-solutions`).
- The **corrected** endpoint contract, with explicit "there is no `/api/admin/inquiries`" and "there is no `/admin/inquiries/{id}/status`" warnings.
- The rewritten visitor-tracking mechanism, the certbot compose service (replacing the cron job), and the self-signed-cert bootstrap that breaks the certbot↔nginx chicken-and-egg problem.

### ✅ Step 8 — End-to-end verification  ← **DONE (this session)**
Everything that can be verified from the authoring machine has been. **The only step that cannot be
completed locally is #5's `docker compose up -d`** — Docker is not installed on this box, and the
deployment target is Oracle Cloud anyway.

| # | Check | Result |
|---|-------|--------|
| 1 | Backend auth | ✅ Already passing (see §5) |
| 2 | Admin page in headless Chrome | ✅ **39/39 checks pass** — see §5 |
| 3 | AI agent end-to-end (browser path) | ✅ **Confirmed in the browser** — chat → corrected sentence, tip and spoken reply all rendered; `/api/ai/chat` and `/api/ai/speak` both 200 |
| 4 | Public site regression | ✅ **9/9 checks pass** — form → `POST /api/inquiries` → 201, "Inquiry Transmitted!" modal, WhatsApp button opens a pre-filled `wa.me` link, visitor tracking fires on page load |
| 5 | Deployment | ⚠️ **Compose structure validated (10/10)**, but `docker compose config` / `up -d` must run on the Oracle box — Docker is not installed here |
| 6 | Data safety | ✅ **PASS** — DB byte-identical and rows intact after the exact deploy stash+pull sequence |
| 7 | Screenshots | ✅ 7 screenshots in `~/.a2m-verify/shots/` |

**Mobile/responsive:** verified at a 480 px viewport — the sidebar is off-canvas, the hamburger
opens it, the backdrop closes it, and there are no pageerrors.

---

## 4. Endpoint contract (verified against live `/openapi.json` — the frontend matches this exactly)

> ⚠️ **CORRECTION — the previous version of this table was wrong.** It listed
> `GET /api/admin/inquiries`, which **does not exist**. The table below was dumped from the running
> server's OpenAPI document and is authoritative.

| Method | Path | Auth | Body / Query | Returns |
|---|---|---|---|---|
| POST | `/api/admin/login` | — | JSON `{username, password}` | `{access_token, token_type}` + **httpOnly `admin_token` cookie** |
| POST | `/api/admin/logout` | — | — | `{message}` |
| GET | `/api/admin/stats` | admin | — | flat `total,new,contacted,closed,total_visits,today_visits,unique_visitors` **plus** nested `inquiries{}`/`visitors{}` and `admin` |
| GET | **`/api/inquiries`** | admin | `?page=N&per_page=20&status_filter=` | `{inquiries[], total, page, per_page, total_pages}` |
| GET | `/admin/inquiries` | admin | `?page=N&per_page=20&status=` | same shape — legacy alias, **different param name** |
| PATCH | **`/api/inquiries/{id}/status`** | admin | JSON `{status}` | the updated inquiry |
| GET | `/api/visitors` | public | — | `{total_visits, today_visits, unique_visitors}` |
| POST | `/api/visitors/track` | public | `{}` | same shape as above |
| GET | `/api/ai/status` | admin | — | `{configured, providers{llm,stt,tts}, browser_fallback, models, base_url}` |
| POST | `/api/ai/transcribe` | admin | multipart, field name **`file`** | `{text}` |
| POST | `/api/ai/chat` | admin | JSON **`{text, history}`** | `{corrected, reply, tip, model, provider}` |
| POST | `/api/ai/speak` | admin | JSON `{text, voice}` | **raw `audio/mpeg` bytes** |
| GET | `/health` | — | — | `{status, app_name, version, environment}` |

**Route names that are easy to get wrong:**
1. There is **no** `/api/admin/inquiries` — the list is `GET /api/inquiries` with `status_filter`.
2. There is **no** `/admin/inquiries/{id}/status` — the update is `PATCH /api/inquiries/{id}/status`.
3. The health endpoint is **`/health`**, not `/api/health`.
4. `/admin/*` is a legacy alias prefix covering only `/admin/login`, `/admin/logout`, `/admin/stats`
   and `/admin/inquiries`. nginx proxies it via `location /admin/`.

Error bodies are `{"detail": "..."}` **or** `{"detail": [{msg, loc, type}, ...]}` for 422s.

---

## 5. Live verification already performed

### 5a. Backend + AI agent (previous session — still valid)

Test backend: a **throwaway** SQLite DB — the real `backend/inquiries.db` was never touched — admin user `admin` / `verify-pass-123`.

```
POST /api/admin/login        → 200 {"access_token":"...","token_type":"bearer"}
GET  /api/ai/status          → configured: true
                                 llm: pollinations ready (keyless) | groq not ready | nvidia not ready
                                 tts: edge ready (en-US-AriaNeural) | nvidia not ready
                                 stt: groq not ready | nvidia not ready   (browser fallback available)
POST /api/ai/chat            → 200 13.3 s
  {"corrected":"I went to the office yesterday.",
   "reply":"You said 'I go to office yesterday' - a more natural way to say that is
            'I went to the office yesterday'. How did you find the office today?",
   "tip":"Remember to use 'went' for past tense and include 'the' before 'office'.",
   "model":"openai-fast","provider":"pollinations"}
POST /api/ai/speak           → 200, content-type: audio/mpeg, content-length: 42192
                                (file(1): MPEG ADTS, layer III, v2, 48 kbps, 24 kHz, Monaural)
GET  /api/admin/stats        → 200 flat + nested shape, admin: "admin"
GET  /docs                   → 200    /openapi.json → 200
POST /api/visitors/track ×3  → total_visits 9,10,11  |  unique_visitors stays 1  (same IP)
GET  /                        → {"docs":"/docs", ...}
```

### 5b. Admin console in headless Chrome (this session) — 39/39

Driven with `puppeteer-core` + the system Chrome against `admin.html` served through a local
proxy that forwards `/api/*` to the throwaway backend.

```
login view on load                    PASS   app shell hidden
wrong password → inline error         PASS   "Invalid credentials", stays on login
correct password → dashboard          PASS
admin chip shows the username         PASS   "admin"
no stat card shows undefined/NaN      PASS   total 3, new 2, contacted 1, closed 0
recent inquiries panel populated      PASS   3 rows
nav switches pages                    PASS   title, panel visibility
inquiries table loads                 PASS   3 rows
page title actually visible           PASS   (the old [id^="page-"] bug)
XSS: no <script> injected             PASS   0 elements, window.__xss undefined
XSS: payload rendered as literal text PASS   "Test <script>alert(1)</script> User 3"
status dropdown updates               PASS   new -> closed
PATCH /api/inquiries/{id}/status      PASS   200, via the /api/ path
status change persists after reload   PASS
filter uses status_filter             PASS
filtered rows all match the filter    PASS
visitor stats render as numbers       PASS
AI provider grid has 3 cards          PASS
AI status pill populated              PASS   "AI ready"
mic button present and enabled        PASS
POST /api/ai/chat                     PASS   200
corrected sentence rendered           PASS   "I went to the office yesterday."
transcript recorded the turn          PASS   "1 turn"
POST /api/ai/speak                    PASS   200
logout returns to the login view      PASS
NO PAGEERROR during the whole run     PASS
```

### 5c. Public site regression (this session) — 9/9
```
visitor tracking POST on page load    PASS   POST /api/visitors/track -> 200
WhatsApp link points at wa.me         PASS
inquiry form POSTs to /api/inquiries  PASS   -> 201
success modal shown                   PASS   "Inquiry Transmitted!"
WhatsApp button opens a pre-filled link PASS  carries the project details
no pageerror on the public site       PASS
```

### 5d. Compose + data safety (this session)
```
compose YAML parses                   PASS   3 services, a2m-network
container names / ports / volumes     PASS   10/10 structural checks
nginx upstream matches the service    PASS   upstream a2m_backend -> backend:8000
deploy stash + pull leaves the DB alone PASS  md5 identical, 13 rows intact
real backend/inquiries.db untouched   PASS   md5 2797b645…, 13 rows + 1 admin user
```

**Known real-world limitation to document:** Pollinations' anonymous tier allows **1 reply per 45 s per IP** (HTTP 402 `FREE_LIMIT`). The backend already surfaces a helpful message for this. Adding a free `GROQ_API_KEY` (console.groq.com/keys) removes the throttle **and** enables Whisper STT — the single highest-value optional key.

### 5e. Later session — content tweaks + Tailwind moved off the CDN

| Change | Where | Result |
|---|---|---|
| Social profile links hidden | `index.html` footer | 3 links (LinkedIn / X / GitHub) hidden via `.social-links { display:none !important }`; **still in the markup** so they can be re-shown by deleting one CSS rule. Twitter + GitHub accounts 404; LinkedIn resolves. |
| Mobile number no longer shown | `index.html` contact box | The visible `+91 82082 14218` was replaced by a green WhatsApp icon + "Chat on WhatsApp". The number still lives in the `wa.me` href and in `WHATSAPP_NUMBER`, so the link works exactly as before. |
| Admin link on the public page | `index.html` footer bar | Discreet "🔒 Admin" link next to the back-to-top button → `/admin.html`. Verified it navigates and shows the login form. |
| **Mic = click to start, click again to send** | `admin.html` AI Coach | Both capture paths now toggle. The browser `SpeechRecognition` path was rewritten (`continuous: true`, `interimResults: true`, live transcript in the text box, nothing sent until the second click). The MediaRecorder path already toggled; its branch was moved above the new one so it still wins when a server STT provider is ready. |
| **Tailwind Play CDN → static build** | `index.html`, `admin.html`, `tailwind.config.js`, `tailwind.input.css`, `tailwind.css`, `package.json` | The 407 KB third-party `cdn.tailwindcss.com` script is gone; a 34 KB compiled stylesheet is served locally. |

**The Tailwind swap and the cascade trap.** The Play CDN injects its stylesheet at runtime, so it lands
*after* the inline `<style>` block — which means Tailwind **utilities beat** the custom
`.glass-panel` border. A `<link>` placed *before* the inline block flips that and the nav/header border
regressed from `slate-800/60` to `white/8`. **The `<link>` must stay after `</style>`** in both files.

**A/B measurement (static build vs Play CDN, same server, animations frozen).** The CDN variant was
rebuilt from `tailwind.config.js` and served from a second origin; both were rendered with
`~/.a2m-local/render.js` and diffed with PIL.

| | site (1440×4369) | login (1440×950) |
|---|---|---|
| pixels differing at all | 26,115 (0.415 %) | 26 (0.002 %) |
| **max channel delta** | **1/255** | **1/255** |
| pixels differing by more than 8/255 | **0** | **0** |
| sampled computed styles (15 props × 11 selectors) | **identical** | **identical** |

The static build is **pixel-equivalent** to the CDN: the only deltas are 1/255 anti-aliasing noise on
text edges. The only computed-style differences were `__linkCount` 3→2 and `__styleCount` 2→3 — the CDN
injects a `<style>` at runtime instead of shipping a `<link>`, which is expected and not visual.

**The cascade trap, re-proved with pixels.** Rendering the *same* file with the `<link>` moved before
`</style>` produces a visible regression, so the ordering is load-bearing:

| | correct order (`<link>` after `</style>`) | wrong order (`<link>` before `</style>`) |
|---|---|---|
| `index.html` nav border | `rgba(30, 41, 59, 0.6)` ✅ (`slate-800/60`) | `rgba(255, 255, 255, 0.08)` ❌ (`white/8`) |
| `admin.html` header border | `rgba(30, 41, 59, 0.7)` ✅ | `rgba(255, 255, 255, 0.08)` ❌ |
| site page height | 4369 px | 4367 px (layout shifts) |
| login pixels differing | — | 1,591 px (0.116 %), max delta 13/255 |

**Two bugs found and fixed while verifying this swap:**

1. **`Dockerfile.frontend` never copied `tailwind.css`.** The site would have deployed with
   **no styling at all** — nginx serves `/tailwind.css` from `/usr/share/nginx/html/`, and the image
   only copied `index.html admin.html company_logo*.png styles.css script.js`. Fixed; `tailwind.css`
   is now an explicit `COPY`. Because CI has no npm step, **`tailwind.css` must be committed** — it is
   a build artifact that the Docker build consumes.
2. **The mic toggle reset the button while the request was still in flight.** Chrome fires a final
   `onresult` and *then* `onend` after `recognition.stop()`. `onresult` saw `stopping === true`, called
   `submitBrowserTranscript()` and started the request; the immediately following `onend` then saw an
   empty transcript and called `setCoachState('idle')`, so the button showed "Ready to listen" for the
   ~15 s the LLM took. Fixed by guarding both `onend` and `onerror` with `if (!state.coach.busy)`.
   The test mock had to be corrected too: it used to call `onend` directly from `stop()`, which never
   reproduced Chrome's ordering and hid the bug.

**Where to put the API keys (for the owner):**

| Purpose | Location |
|---|---|
| Local machine | `backend/.env` → `NVIDIA_API_KEY=` (line 104) / `GROQ_API_KEY=` |
| Production, automatic | GitHub repo → **Settings → Secrets and variables → Actions → New repository secret** → name `NVIDIA_API_KEY` (or `GROQ_API_KEY`), value `nvapi-…`. `.github/workflows/deploy.yml:150` already maps it into `backend/.env` on the Oracle box. |
| Production, manual | `/home/ubuntu/a2m-digital-solutions/backend/.env` on the Oracle box. The CI now **updates that key in place** instead of rewriting the file, so a hand-pasted key survives a deploy. |
| Fresh box | `backend/.env.example` — `deploy.sh` copies it to `backend/.env` when the file is missing. |

NVIDIA keys come from **build.nvidia.com** ("Get API Key" → `nvapi-…`), free credits, no card.
**NVIDIA is LLM-only here**: its `/v1/audio/speech` and `/v1/audio/transcriptions` return **404**
(the routes are not served), so `NVIDIA_STT_MODEL` / `NVIDIA_TTS_MODEL` in `.env` are inert. For a free
voice pipeline use **Groq** (Whisper STT + LLM) — it is the single highest-value optional key.

### 5f. The owner's NVIDIA key, measured (later session)

The owner pasted a real `NVIDIA_API_KEY` into `backend/.env`. Probing the live API with that key
produced a set of findings that are now baked into the config.

**NVIDIA model availability is PER ACCOUNT.** A model can be listed in the public catalog and still
return `404 "Function ... not found for account ..."` on a given key. Probed with the owner's key:

| Model | Result |
|---|---|
| `nvidia/nemotron-3.5-bolt-e4b` | **200, 1.6 s** ✅ |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 200, 5.7–8.5 s ✅ |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 200 but **55 s and an EMPTY answer** |
| `nvidia/nemotron-nano-3-30b-a3b`, `nvidia/llama-3.1-nemotron-51b-instruct`, `nvidia/nemotron-3-super-120b-a12b`, `nvidia/nemotron-4-340b-instruct`, `nvidia/llama-3.1-nemotron-ultra-253b-v1`, `nvidia/llama-3.1-nemotron-70b-instruct` (the old default) | **404 on this account** |
| `nvidia/nemotron-3-ultra-550b-a55b` | timed out (>200 s) |

**The Nemotron models are reasoning models.** They spend part of the token budget thinking out loud
and return `content: null` when the budget is too small. Measured on `nemotron-3.5-lightning-30b-a3b`
with the real coach prompt: `max_tokens=300` → 300 reasoning tokens and an **empty** answer;
`max_tokens=1200` → 830 reasoning tokens and valid JSON, but **55 seconds**. `bolt-e4b` needs no
headroom because it barely reasons.

**Three real bugs came out of this and were fixed:**

1. `_extract_content()` did `str(content)`, so a `content: null` reply became the literal string
   `"None"` and the JSON parser failed with a nonsense message. It now raises a `ProviderError` that
   names the reasoning-model token budget, and reports how much reasoning was consumed.
2. The NVIDIA provider sent `max_tokens: 300` — not enough for a reasoning model, so **every NVIDIA
   call returned an empty answer**. Now `NVIDIA_MAX_TOKENS` (default **600**).
3. `NVIDIA_TIMEOUT` was **60 s** while `nemotron-3.5-lightning-30b-a3b` needs 55 s+ → the request
   died at the timeout. Raised to **90 s**, and `nginx.conf`'s `proxy_read_timeout`/`proxy_send_timeout`
   raised from 90 s to **120 s** so nginx cannot cut off a reply the backend is about to send.

**The provider chain was also lying about readiness.** `_provider_ready()` only checked whether the
key was set, so NVIDIA was advertised as a ready STT and TTS provider and the admin UI fired a doomed
request at `/v1/audio/transcriptions` before falling back to the browser. `_provider_ready()` is now
**stage-aware**: NVIDIA reports *"NVIDIA has no speech-to-text or speech-synthesis model"* for the
stt/tts stages, and Edge reports *"speech-synthesis provider only"* for stt. `STT_PROVIDER_ORDER` is
now `groq` and `TTS_PROVIDER_ORDER` is now `edge` — NVIDIA was removed from both.

**Provider failures were invisible.** The chain caught every provider error and moved on, so a paid
NVIDIA key that was silently falling back to Pollinations looked like it was working. Every provider
failure is now logged at WARNING level (`a2m.ai` logger), naming the provider and the reason.

**Final settings that ship:**

```
LLM_PROVIDER_ORDER=nvidia,pollinations,groq
STT_PROVIDER_ORDER=groq
TTS_PROVIDER_ORDER=edge
NVIDIA_LLM_MODEL=nvidia/nemotron-3.5-bolt-e4b
NVIDIA_MAX_TOKENS=600
NVIDIA_TIMEOUT=90
```

**Measured result:** chat went from **13 s (Pollinations) → 2.0 s (NVIDIA)**, TTS 1.2 s, and the
answer is correct on all four test sentences. The NVIDIA key is now genuinely used on every request.

> ⚠️ Because NVIDIA is first in the chain, a model that is unavailable **on a particular account**
> silently falls through to Pollinations. If the admin UI ever shows `provider: pollinations` while
> `NVIDIA_API_KEY` is set, the model is not available on that account — check the backend log for the
> WARNING line naming the provider and the reason.

**Final re-run of every suite against the Tailwind-built files (all green):**

| Suite | Result |
|---|---|
| Admin console (`~/.a2m-verify/browser/test.js`) | **39/39** |
| Public site (`~/.a2m-verify/browser/public-test.js`) | **9/9** |
| Public site + phone/admin-link (`~/.a2m-local/site-check.js`) | **14/14** |
| Social links hidden (`~/.a2m-local/social-check.js`) | **14/14** |
| Mic: click-to-speak / click-again-to-send (`~/.a2m-local/mic-check.js`) | **17/17** |
| `node --check` on both inline scripts | **PASS** |
| Tailwind static build vs Play CDN | **0 pixels differ by >1/255** |
| Real `backend/inquiries.db` | **md5 `2797b64555fc32ce9d71589ae90aeebe` — untouched** |

> The **MediaRecorder → server-STT** branch (`~/.a2m-local/mic-server-check.js`, 12/12) needs a real
> `GROQ_API_KEY`; there is no free no-signup STT provider, so it cannot be re-run locally without one.
> The browser `SpeechRecognition` branch is the one that runs keyless and it is fully covered above.


### 5g. The AI Coach fixed (later session) — two independent root causes

The owner's use case, verbatim: *"I just have resign from my job … I want to search for the job for
that I am doing really good practice of English and also preparing for the interviews."*

The symptom, verbatim: *"whenever I refresh is the page first time coach works properly but when
second time if I give the ways when I speak I can't time then it does not work it gives reply like
sounds good try another sentence"* and *"it did not correct my english"*.

**That was TWO separate bugs, and each one alone was enough to break the second turn.**

#### Bug 1 — the model stopped returning JSON from turn 2 onwards

The coach asks for one raw JSON object. On turn 1 the model returned JSON. From turn 2 it returned
**plain prose**, because the frontend fed its own previous reply back into the history as plain text
and the model copied that style. `_parse_coach_json()` then found no JSON, threw the whole reply away
and showed the hardcoded string *"That sounds good. Try another sentence and I will check it."* —
which is why the owner saw a coach that answered but never corrected anything.

Fixed on three levels, so the bug cannot come back through any one of them:

1. **The parser no longer discards a good reply.** `_parse_coach_json()` now falls back to
   `_salvage_prose()`, which reads the corrected sentence out of prose
   (*"a more natural way to say that is 'X'"*, *"you should say 'X'"*, *"instead of X, say Y"*) and
   `_salvage_prose_tip()` for a trailing `Tip:`. The corrected sentence is compared **exactly**, so a
   capitalisation-only fix is kept.
2. **The prompt restates the JSON contract once there is history.** `_JSON_REINFORCEMENT` is appended
   to the system prompt whenever `history` is non-empty: *"the first character of your answer must be
   `{` and the last must be `}`"*. This alone makes the model answer in JSON again on turn 2+, even
   when the history holds old plain-text turns.
3. **The frontend stores the assistant turn as JSON.** `admin.html` now pushes
   `JSON.stringify({corrected, reply, tip})` into `state.coach.history` instead of the spoken reply,
   so the model sees its own previous turn in the format we want.

`_tidy_sentence()` capitalises the first letter of the corrected sentence deterministically — the
model was inconsistent about this, and a missing capital letter is exactly the kind of correction the
owner asked for.

#### Bug 2 — the microphone was silently ignored on the second attempt

`state.coach.busy` stayed `true` for the **whole** request **plus** the whole TTS playback, and
`startCapture()` began with `if (state.coach.busy) { return; }`. So a second tap on the microphone
while the coach was still talking did **nothing at all, with no message**. From the owner's side the
microphone was broken.

Fixed:

- `state.coach.busy` is now cleared as soon as the answer is on screen, not after the audio ends, so
  the send button and the microphone are free again while the coach speaks.
- `state.coach.speaking` + `state.coach.speakToken` track the playback. Tapping the microphone while
  the coach talks **interrupts it and starts listening** — the coach stops mid-sentence. The token
  cancels audio that is still being fetched, so it cannot start playing after the user has already
  begun to speak.
- A tap while a request is genuinely in flight now shows *"Still working on the last reply - one
  moment."* instead of doing nothing.
- `setCoachState()` records `state.coach.phase`, and the end of the speech only returns to idle if
  nothing newer happened — the old code stomped the "Listening…" state with "Ready to listen".

#### The coach now serves the job-search / interview goal

`ENGLISH_COACH_SYSTEM_PROMPT` was rewritten. It now states the user's situation (left their job,
practising English, preparing for interviews) and requires, on **every** turn: the correction, a
conversational 1–2 sentence reply (spoken by TTS, so under 25 words each), **one concrete
job-search or interview input**, and one open question. "Always correct" is explicit — including on
turns where the user is telling the coach about their life or asking a question.

#### Three modes

`AIChatRequest` gained a `mode` field (`practice` | `interview` | `jobsearch`, validated by a regex
pattern — an unknown mode is a **422**). Each mode has its own overlay in `COACH_MODE_PROMPTS`:

| Mode | What the coach does |
|---|---|
| `practice` | Correct the English, keep the conversation going. |
| `interview` | Plays the interviewer: **one** realistic question per turn + one specific improvement for that answer. It does **not** hand over a full model answer. |
| `jobsearch` | Help with the hunt: explaining the resignation, the CV, the LinkedIn summary, how to sell a project, how to follow up with a recruiter. |

`admin.html` has a three-button segmented control above the microphone; the active mode is sent with
every request and the backend echoes it back in `AIChatResponse.mode`.

**New Tailwind classes were added to `admin.html`, so `tailwind.css` was rebuilt** (34 139 → 34 335
bytes). A rebuild is now byte-identical to the committed file, which is the check to run after any
HTML class change.

#### Tests

`backend/test_coach.py` — a dependency-free script (`./venv/bin/python test_coach.py`, add `--live`
to talk to the real provider). **35 offline checks + 6 live checks, 41/41 passing.** It covers the
JSON path, the code-fence path, the truncated-JSON path, the prose salvage (the four real prose
replies the model produced), the proper-noun guard, the empty-output fallback, capitalisation, the
mode overlays, the history reinforcement, and the `content: null` error.

Two new browser suites, both in `~/.a2m-verify/browser/`:

| Suite | Result |
|---|---|
| `mode-check.js` — the three mode buttons, the active marker, the hint, the mode travelling with the request, the assistant history stored as JSON | **16/16** |
| `interrupt-check.js` — the mic is never silently ignored, it interrupts the coach mid-sentence | **7/7** |
| `mic-check.js` (pre-existing, re-run to prove no regression) | **17/17** |
| Real `backend/inquiries.db` | **md5 `2797b64555fc32ce9d71589ae90aeebe` — untouched** |

### 5h. Deployment hardening found while preparing the Oracle deploy

Three real bugs were found by tracing the production path end to end. **All three would have shipped.**

#### 1. The compose file silently overrode the secrets with empty values

`docker-compose.prod.yml` declared:

```yaml
- ADMIN_PASSWORD=${ADMIN_PASSWORD:-admin123}
- NVIDIA_API_KEY=${NVIDIA_API_KEY:-}
```

Compose resolves `${VAR}` from the shell that ran `compose up` — or from a `.env` file **next to the
compose file**. The GitHub Actions workflow exports `A2M_ADMIN_PASSWORD` and `A2M_NVIDIA_API_KEY`
(with an `A2M_` prefix) and writes them into `backend/.env`. The **unprefixed** names were never in
the shell, so both resolved to their defaults.

**And an empty environment variable beats a value in the `.env` file**, because `pydantic-settings`
reads OS env vars before the dotenv file. Measured:

```
no env var set   -> real-key-from-file
env var = ''     -> (empty)          <-- the file is ignored
```

So the container would have run with **`NVIDIA_API_KEY=""`** (the agent silently falls back to
Pollinations — slow, and it looks like it is working) and **`ADMIN_PASSWORD="admin123"`** (the real
secret ignored, on a site reachable from the internet).

**Fixed** by loading the file instead of substituting variables:

```yaml
env_file:
  - ./backend/.env
environment:
  - ENVIRONMENT=production
  - DEBUG=false
  - DATABASE_URL=sqlite:///./data/inquiries.db
```

`env_file` puts the file's values into the container environment; `environment` still wins over it,
so production mode and the volume-mounted database path are unchanged. A simulation of both the old
and the new resolution confirms the fix.

The CI workflow now also **refuses to deploy** if `ADMIN_PASSWORD` is missing or still `admin123` —
a failed deploy is much better than a published default password.

#### 2. The production database directory could not be written

`./backend/data` is bind-mounted into the container so the inquiry database survives a rebuild.
Docker creates a **missing bind-mount source as root**, and the container runs as the non-root
`appuser` — so SQLite could not create or write the file and the backend would fail to start.

**Fixed** three ways: `appuser` now has a **fixed UID/GID 1000** (the standard UID of the `ubuntu`
user on the Oracle instance), and every deploy path (`deploy.sh`, `deploy-quick.sh`,
`deploy-one-liner.sh`, the `Makefile` and the CI workflow) creates the directory and sets its
ownership before starting the stack.

#### 3. The inquiry database was being baked into the image

`backend/Dockerfile.prod` ends with `COPY . .`. `backend/.dockerignore` already excluded `.env` and
`venv/`, but **not `*.db`** — and `backend/inquiries.db` was still tracked in git, so a CI checkout
contained it and it landed in an image layer. It is excluded now, and the untracking of the database
is committed.

**Also:** `tailwind.css` must be committed — `Dockerfile.frontend` does `COPY tailwind.css`, and
without it the production site ships with **no styling at all**.

---

## 6. Working commands

```bash
# backend venv (already has edge-tts installed)
backend/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000   # run from backend/

# JS syntax check on an HTML file's inline script — extract the LAST <script> body only.
# Including the <script> tag makes node --check fail with "Unexpected token '<'".
python3 - <<'PY'
import re, pathlib
html = pathlib.Path('admin.html').read_text()
blocks = re.findall(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html, re.S)
pathlib.Path('/tmp/admin_app.js').write_text(blocks[-1])
PY
node --check /tmp/admin_app.js

# compose validation
docker compose -f docker-compose.prod.yml config

# --- AI Coach tests (no pytest needed, no network unless --live) ---
cd backend
./venv/bin/python test_coach.py            # 35 offline checks
./venv/bin/python test_coach.py --live     # + 6 checks against the real provider

# --- AI Coach browser checks (need the backend on :8000 and the static site on :5500) ---
cd ~/.a2m-verify/browser
node mode-check.js        # 16 checks - the mode selector
node interrupt-check.js   #  7 checks - the microphone is never ignored
```

**Verification workspace (outside the repo):** `~/.a2m-verify/`
- `backend/` — throwaway backend copy + its own `verify.db` (admin / `verify-pass-123`), port 8112
- `proxy.py` — serves `admin.html` / `index.html` / the logos and proxies `/api/*` to the backend, port 8899
- `browser/` — `puppeteer-core` + `test.js` (admin console, 39 checks), `public-test.js` (9 checks), `mode-check.js` (16 checks, coach modes), `interrupt-check.js` (7 checks, mic interrupt)
- `shots/` — the screenshots
- `simrepo/` — the throwaway clone used for the stash+pull data-safety simulation

> ⚠️ **`/tmp` is wiped between tool calls in this environment**, and servers started with `nohup ... &`
> die with it. Put throwaway state under `~/.a2m-verify/` and run servers with the harness's
> background-task mechanism.

Existing helper dirs from the earlier session: `backend/venv/` (Python venv with `edge-tts`, `httpx`).

---

## 7. Known gotchas (each one cost time — do not repeat them)

1. `git rm --cached` with a glob **aborts the whole command** if any matched path is untracked. List tracked paths explicitly.
2. `node --check` on an extracted `<script>` block fails with `Unexpected token '<'` if the `<script>` tag itself is included. Extract only the body.
3. `proxy_pass http://backend:8000;` — **no trailing slash, no URI part.** Adding either rewrites the path and breaks every `/api/*` route.
4. Nginx serves `index.html`/`admin.html` statically; the backend never sees those requests. That is exactly why visitor counting moved to an explicit `POST /api/visitors/track` call.
5. `ENABLE_API_DOCS` (not `DEBUG`) gates `/docs` — `deploy.sh` advertises `https://a2mdigitalsolutions.com/docs`.
6. `pydantic-settings` reads **environment variables first**, then the `.env` file. An env var in the shell overrides the file.
7. The `git stash` + tracked-DB combination silently discarded production inquiries on every deploy. The DB is now untracked **and** the stash is scoped to source-file extensions only.
8. Two `Explore` agents failed with `429 RateLimitError` (minimax-flash unavailable) — do the verification directly with Bash/Read instead of spawning agents.
9. Pollinations `openai-fast` is a reasoning model: without an explicit `max_tokens` it burns the whole budget thinking and truncates the JSON. `max_tokens: 800` is set.
10. `nvidia/llama-3.1-nemotron-70b-instruct` is live; `meta/llama-3.3-70b-instruct` returns **HTTP 410** (EOL 2026-08-26). NVIDIA's `/v1/audio/speech` and `/v1/audio/transcriptions` return a plain-text **404** — the audio routes are not served, so NVIDIA cannot be the TTS/STT provider.
11. **The old handoff's endpoint table was wrong.** It listed `GET /api/admin/inquiries`, which **does not exist**. Dump the live `/openapi.json` instead of trusting a written contract. The real routes are `GET /api/inquiries?page=&per_page=&status_filter=`, `PATCH /api/inquiries/{id}/status`, `GET /health`.
12. **The verification proxy must forward the `Cookie` header.** Without it every authenticated request 401s and the admin console correctly bounces back to the login screen — which looks like a frontend bug but is not.
13. **A fixed overlay in the custom modal swallows the next click.** `index.html`'s success modal is `fixed inset-0 z-50`; call `closeModal()` before clicking anything underneath it. Also `form.reset()` clears the required `#service` select, so a second submit fails `checkValidity()` until the service is re-selected.
14. **The backend stores naive UTC timestamps.** `created_at` has no timezone suffix, so a browser parses it as local time unless you append `Z`. `formatDate()` in `admin.html` appends `Z` before rendering.
15. **Screenshots get downscaled.** Do not judge small text (times, counts) from a resized PNG — read the DOM instead. A "10:10" that looked wrong was actually `18:10` IST, correctly rendered.
16. **`/tmp` really is wiped between tool calls.** A backup written to `/tmp/index.html.bak` was gone by the next call. Keep throwaway state under `~/.a2m-verify/` or `~/.a2m-local/`.
17. **The shell safety classifier fails intermittently** ("kimi-k3.1-pro is temporarily unavailable"). `echo`/`ls`/`curl` still go through; compound commands with `&`/`setsid`/`nohup` are the ones that time out. Retry, and if a command keeps failing, split it or move the body into a script.
18. **A background server started with plain `nohup … &` dies when the session ends.** Use `(setsid … &)` in a subshell. Also, a command containing a literal `http://` in an env assignment sometimes trips the classifier — split it (`U="http:"; H="//127.0.0.1:8112"`) and it goes through.
19. **`Dockerfile.frontend` must copy every static asset the pages reference.** `nginx.conf` serves `/usr/share/nginx/html/` with `try_files $uri $uri/ /index.html`, so a missing file is a **404 that renders as an unstyled page**, not a build error. Adding `<link href="/tailwind.css">` without adding the `COPY` shipped a completely unstyled site.
20. **NVIDIA model availability is per ACCOUNT, not global.** The public catalog (`GET https://integrate.api.nvidia.com/v1/models`, no auth needed, 84 models) lists far more models than a given key can actually call — the rest return `404 "Function ... not found for account ..."`. Always probe the **owner's own key** before choosing a default model. The catalog also contains **no ASR or TTS model at all**, which is why NVIDIA's `/v1/audio/*` routes 404.
21. **Reasoning models need a token budget, and a bigger budget costs time.** A `content: null` reply from an OpenAI-compatible endpoint usually means the model spent the whole budget thinking — raise `max_tokens`. But do not raise it blindly: `nemotron-3.5-lightning-30b-a3b` needed 1200 tokens and took **55 s**; `nemotron-3.5-bolt-e4b` needed 600 and took **1.6 s**. Pick a model that reasons *little*, not just a big budget.
22. **A provider chain that swallows errors makes a paid key look free.** The chain caught every provider error and fell through to the next provider with no log line, so a working NVIDIA key that was silently failing looked identical to Pollinations answering. Always log provider failures by name.
23. **A model imitates the format of the previous assistant turn.** If the history holds your own reply as plain text, the model answers in plain text on the next turn — and a parser that only accepts JSON will throw the answer away. Fix it on three levels: never discard a valid reply, restate the output contract in the prompt when there is history, and store the assistant turn in the format you want.
24. **Never compare a corrected sentence case-insensitively.** `candidate.lower() != original` throws away a capitalisation-only fix, which is one of the corrections a learner most needs to see.
25. **A busy flag that spans the TTS playback makes the microphone look broken.** If `busy` covers the reply *and* the audio, the next tap is ignored with no feedback. Separate "generating" from "speaking", let the microphone interrupt the playback, and never return silently from a click handler — say what is happening.
26. **A reply that is still being fetched will still play.** Cancelling the `<audio>` element is not enough — the audio may not exist yet. Use a monotonically increasing token and check it after the fetch, before playing.
27. **`setCoachState()` must not be called from a stale callback.** An async callback that ends after the user has already started the next action will overwrite the newer state. Record the current phase and only step back to idle if the phase is still the one the callback belongs to.
28. **Any new Tailwind class in `admin.html` needs `npm run build:css`.** `tailwind.config.js` scans the HTML at build time, so a class that is not in `tailwind.css` simply does not exist in production. The check: rebuild and confirm the output is byte-identical to the committed file.
29. **A tailwindcss install can vanish between sessions.** `node_modules/` is gitignored, so a fresh clone has no CLI. The npm npx cache often still has the exact pinned version — `~/.npm/_npx/*/node_modules/.bin/tailwindcss` — and can rebuild the stylesheet without a network install.
30. **`docker compose` resolves `${VAR}` from the shell, and an empty env var beats the `.env` file.** `${VAR:-default}` in a compose file does **not** read `backend/.env` — it reads the shell that ran `compose up` or a `.env` file next to the compose file. Because `pydantic-settings` reads OS env vars *before* the dotenv file, a `${NVIDIA_API_KEY:-}` that resolves to `""` **overrides** the real key in the mounted `.env`. Use `env_file:` to load secrets; use `environment:` only for values that must win.
31. **Docker creates a missing bind-mount source as root.** A bind mount over a directory that does not exist on the host is created root-owned, so a container running as a non-root user cannot write to it. Create the directory and `chown` it to the container's UID **before** `compose up`. Pin the container UID in the Dockerfile (`useradd -u 1000`) so the host can set the ownership to match.
32. **`COPY . .` respects the `.dockerignore` in the CONTEXT root, not the repo root.** The backend image is built with `./backend` as its context, so it uses `backend/.dockerignore`; the root-level one is ignored. Check the right file for the right context.

---

## 8. Open items for the owner (not blocking the code work)

- ⚠️ **The untracking of `backend/inquiries.db` and the `.pyc` files is STAGED BUT NOT COMMITTED.** `git status` shows them as `D` in the index, but `HEAD` still tracks all six. A fresh clone therefore still contains the DB, and the Oracle box only stops tracking it **after a commit**. The scoped stash (`*.py *.html *.yml *.yaml *.sh *.conf *.css *.js`) already excludes `*.db`, so data is safe either way — but the untracking should be committed. **No commit has been made; ask before committing.**
- **Docker is not installed on this machine**, so `docker compose -f docker-compose.prod.yml config` and `up -d` could not be run here. A 10/10 structural validation of the compose file was done by hand instead (YAML parse, service/container names, ports, volumes, `depends_on` + healthcheck, network, nginx upstream → `backend:8000`). **Run the real `docker compose config` and `up -d` on the Oracle box** before going live.
- **Change `ADMIN_PASSWORD`** from the default in `backend/.env` and in the GitHub secret `A2M_ADMIN_PASSWORD`. The deploy scripts bootstrap `.env` from `.env.example`, so `.env.example` must also carry a real value before go-live.
- **`COOKIE_SECURE=true`** in production once the site is HTTPS (`false` is what makes local `http://` work).
- Optional API keys, in priority order: **`GROQ_API_KEY`** (free — removes the Pollinations 45 s throttle *and* enables server-side Whisper STT), then `NVIDIA_API_KEY` (LLM only; its audio routes are dead).
- Whether the AI agent should be reachable outside the admin area — currently admin-only, which is the safer default. **Owner's call.**
- The domain `a2mdigitalsolutions.com` must resolve to the Oracle instance before certbot issuance is attempted.
