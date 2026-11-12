"""
A2M Digital Solutions - FastAPI Backend
Handles inquiry form submissions, email notifications, admin dashboard, and visitor tracking
"""
from contextlib import asynccontextmanager
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, HTTPException, status, Response, Cookie, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
import secrets
import hashlib

from config import get_settings
from database import (
    init_db, get_db, create_inquiry, get_inquiries, get_inquiry,
    update_inquiry_status, get_inquiry_stats, increment_visitor_count,
    register_visit,
    get_visitor_stats, get_admin_user, create_admin_user, update_last_login,
    create_admin_session, get_admin_session, delete_admin_session,
    purge_expired_sessions,
    AdminUser, VisitorCount
)
from models import (
    InquiryCreate,
    InquiryResponse,
    InquiryListResponse,
    InquiryStatusUpdate,
    StatsResponse,
    HealthResponse,
    ErrorResponse,
    AdminLogin,
    AdminToken,
    VisitorStats,
    AIChatRequest,
    AIChatResponse,
    AISpeakRequest
)
from email_service import send_inquiry_email
from ai_agent import (
    transcribe_audio,
    coach_reply,
    synthesize_speech,
    ai_status,
)

settings = get_settings()

# auto_error=False so a missing Basic header does not short-circuit the
# cookie-based session check below.
security = HTTPBasic(auto_error=False)

PBKDF2_ITERATIONS = 260000


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random salt"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash (supports legacy unsalted sha256)"""
    if not hashed_password:
        return False

    if hashed_password.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt_hex, digest_hex = hashed_password.split("$")
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode(),
                bytes.fromhex(salt_hex),
                int(iterations),
            )
            return secrets.compare_digest(digest.hex(), digest_hex)
        except (ValueError, TypeError):
            return False

    # Legacy hashes created by earlier versions of this backend
    return secrets.compare_digest(
        hashlib.sha256(plain_password.encode()).hexdigest(), hashed_password
    )


def create_access_token() -> str:
    """Create a simple session token"""
    return secrets.token_urlsafe(32)


def verify_admin(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security),
    db: Session = Depends(get_db)
):
    """
    Authenticate the admin dashboard.

    Accepts either:
      * the `admin_token` session cookie issued by /api/admin/login (browser flow), or
      * HTTP Basic credentials (scripted/API access).
    """
    token = request.cookies.get("admin_token")
    if token:
        session = get_admin_session(db, token)
        if session and session.expires_at > datetime.utcnow():
            admin = db.query(AdminUser).filter(AdminUser.id == session.admin_id).first()
            if admin and admin.is_active:
                return admin
        # Expired or orphaned session - drop it
        delete_admin_session(db, token)

    if credentials is not None:
        admin = get_admin_user(db, credentials.username)
        if admin and admin.is_active and verify_password(credentials.password, admin.password_hash):
            return admin

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Basic"},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    init_db()

    # Create / sync the admin user from the environment
    db = next(get_db())
    admin = get_admin_user(db, settings.ADMIN_USERNAME)
    if not admin:
        create_admin_user(db, settings.ADMIN_USERNAME, hash_password(settings.ADMIN_PASSWORD))
        print(f"Created admin user: {settings.ADMIN_USERNAME}")
    elif not verify_password(settings.ADMIN_PASSWORD, admin.password_hash):
        # ADMIN_PASSWORD changed in .env - keep the database in sync
        admin.password_hash = hash_password(settings.ADMIN_PASSWORD)
        db.commit()
        print(f"Updated admin password for: {settings.ADMIN_USERNAME}")
    purge_expired_sessions(db)
    db.close()

    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"📧 Email provider: {settings.EMAIL_PROVIDER}")
    print(f"🗄️  Database: {settings.DATABASE_URL}")
    ai = ai_status()
    ready_llm = next((p["name"] for p in ai["providers"]["llm"] if p["ready"]), "none")
    ready_tts = next((p["name"] for p in ai["providers"]["tts"] if p["ready"]), "none")
    print(f"🤖 AI Agent: LLM={ready_llm} TTS={ready_tts}")
    if settings.NVIDIA_API_KEY:
        print("🔑 NVIDIA NIM: configured (optional provider)")
    if settings.GROQ_API_KEY:
        print("🔑 Groq: configured (optional provider)")
    yield
    # Shutdown
    print("👋 Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for A2M Digital Solutions inquiry form with admin dashboard",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Visitor Tracking Middleware
@app.middleware("http")
async def track_visitors(request: Request, call_next):
    """Track visitor count.

    The counter is incremented by the frontend calling POST /api/visitors/track
    on page load, not here: in production nginx serves the HTML directly, so
    the backend never sees the page request itself. Counting every request the
    backend happens to see would only count API traffic.
    """
    return await call_next(request)


# Rate limiting middleware (simple in-memory)
request_counts = {}

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting by IP"""
    if not settings.DEBUG:
        client_ip = request.client.host
        key = f"{client_ip}:{request.url.path}"

        if key not in request_counts:
            request_counts[key] = {"count": 0, "window_start": 0}

        import time
        current_time = int(time.time() / 60)  # 1-minute windows

        if request_counts[key]["window_start"] != current_time:
            request_counts[key] = {"count": 1, "window_start": current_time}
        else:
            request_counts[key]["count"] += 1

        if request_counts[key]["count"] > settings.RATE_LIMIT:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Please try again later."}
            )

    response = await call_next(request)
    return response


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(detail=exc.detail, error_code=str(exc.status_code)).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(detail="Internal server error", error_code="500").model_dump()
    )


# Health check
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT
    )


# Visitor Stats (Public)
@app.get("/api/visitors", response_model=VisitorStats, tags=["Visitors"])
async def get_visitor_stats_endpoint(db: Session = Depends(get_db)):
    """Get visitor statistics"""
    stats = get_visitor_stats(db)
    return VisitorStats(**stats)


@app.post("/api/visitors/track", response_model=VisitorStats, tags=["Visitors"])
async def track_visitor(request: Request, db: Session = Depends(get_db)):
    """Record one page view.

    The public site calls this once per page load. The backend derives the
    visitor's address from the request, so a reload counts as a new visit
    while the same visitor counts once towards the daily unique total.
    """
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else ""
    register_visit(db, client_ip)
    stats = get_visitor_stats(db)
    return VisitorStats(**stats)


# Inquiry endpoints
@app.post(
    "/api/inquiries",
    response_model=InquiryResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Inquiries"],
    summary="Submit a new inquiry"
)
async def submit_inquiry(
    inquiry: InquiryCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Submit a new project inquiry.
    """
    inquiry_data = inquiry.model_dump()
    inquiry_data["ip_address"] = request.client.host
    inquiry_data["user_agent"] = request.headers.get("user-agent", "")

    db_inquiry = create_inquiry(db, inquiry_data)

    # Send email notification (async, non-blocking)
    import asyncio
    email_data = {
        "name": inquiry.name,
        "email": inquiry.email,
        "phone": inquiry.phone,
        "service": inquiry.service,
        "timeline": inquiry.timeline,
        "message": inquiry.message
    }
    asyncio.create_task(send_inquiry_email(email_data))

    return InquiryResponse.model_validate(db_inquiry)


@app.get(
    "/api/inquiries",
    response_model=InquiryListResponse,
    tags=["Inquiries"],
    summary="List inquiries (admin)"
)
async def list_inquiries(
    page: int = 1,
    per_page: int = 20,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin)
):
    """
    List all inquiries with pagination and optional status filter.
    Requires admin authentication.
    """
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 20

    skip = (page - 1) * per_page
    inquiries = get_inquiries(db, skip=skip, limit=per_page, status=status_filter)
    total = db.query(__import__('database', fromlist=['Inquiry']).Inquiry).count()

    if status_filter:
        total = db.query(__import__('database', fromlist=['Inquiry']).Inquiry).filter(
            __import__('database', fromlist=['Inquiry']).Inquiry.status == status_filter
        ).count()

    return InquiryListResponse(
        inquiries=[InquiryResponse.model_validate(i) for i in inquiries],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page
    )


@app.get(
    "/api/inquiries/{inquiry_id}",
    response_model=InquiryResponse,
    tags=["Inquiries"],
    summary="Get a single inquiry"
)
async def get_inquiry_by_id(inquiry_id: int, db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    """Get a single inquiry by ID"""
    inquiry = get_inquiry(db, inquiry_id)
    if not inquiry:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    return InquiryResponse.model_validate(inquiry)


@app.patch(
    "/api/inquiries/{inquiry_id}/status",
    response_model=InquiryResponse,
    tags=["Inquiries"],
    summary="Update inquiry status"
)
async def update_inquiry_status_endpoint(
    inquiry_id: int,
    status_update: InquiryStatusUpdate,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin)
):
    """Update inquiry status (new, contacted, closed)"""
    inquiry = update_inquiry_status(db, inquiry_id, status_update.status)
    if not inquiry:
        raise HTTPException(status_code=404, detail="Inquiry not found")
    return InquiryResponse.model_validate(inquiry)


@app.get(
    "/api/stats",
    response_model=StatsResponse,
    tags=["Inquiries"],
    summary="Get inquiry statistics"
)
async def get_stats(db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    """Get inquiry statistics"""
    stats = get_inquiry_stats(db)
    return StatsResponse(**stats)


# Admin Login
@app.post("/api/admin/login", response_model=AdminToken, tags=["Admin"], summary="Admin login")
@app.post("/admin/login", response_model=AdminToken, tags=["Admin"], include_in_schema=False)
async def admin_login(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Admin login.

    Accepts a JSON body {"username": ..., "password": ...} (urlencoded form bodies
    are also accepted for backwards compatibility) and issues an httpOnly session
    cookie that the dashboard then uses for every subsequent request.
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
    else:
        try:
            payload = dict(await request.form())
        except Exception:
            payload = {}

    try:
        credentials = AdminLogin(**payload)
    except Exception:
        # Never reveal which field was wrong
        raise HTTPException(status_code=401, detail="Invalid credentials")

    admin = get_admin_user(db, credentials.username)
    if not admin or not admin.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(credentials.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create a server-side session and hand the browser an httpOnly cookie
    token = create_access_token()
    expires_at = datetime.utcnow() + timedelta(hours=settings.ADMIN_SESSION_HOURS)
    create_admin_session(db, token, admin.id, expires_at)

    # Update last login
    update_last_login(db, admin.id)

    # Set cookie
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.ADMIN_SESSION_HOURS * 3600,
        path="/",
    )

    return AdminToken(access_token=token)


@app.post("/api/admin/logout", tags=["Admin"], summary="Admin logout")
@app.post("/admin/logout", tags=["Admin"], include_in_schema=False)
async def admin_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Admin logout - clears the session cookie and the stored session"""
    token = request.cookies.get("admin_token")
    if token:
        delete_admin_session(db, token)
    response.delete_cookie(key="admin_token", path="/")
    return {"message": "Logged out successfully"}


# Admin Dashboard Stats
@app.get("/api/admin/stats", tags=["Admin"], summary="Dashboard statistics")
@app.get("/admin/stats", tags=["Admin"], include_in_schema=False)
async def admin_stats(db: Session = Depends(get_db), admin=Depends(verify_admin)):
    """Get dashboard statistics (flat fields + grouped breakdowns)"""
    inquiry_stats = get_inquiry_stats(db)
    visitor_stats = get_visitor_stats(db)
    return {
        **inquiry_stats,
        "total_visits": visitor_stats.get("total_visits", 0),
        "today_visits": visitor_stats.get("today_visits", 0),
        "unique_visitors": visitor_stats.get("unique_visitors", 0),
        "inquiries": inquiry_stats,
        "visitors": visitor_stats,
        "admin": getattr(admin, "username", str(admin)),
    }


# Admin - List Inquiries with pagination
@app.get("/admin/inquiries", tags=["Admin"])
async def admin_list_inquiries(
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin)
):
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 20

    skip = (page - 1) * per_page
    inquiries = get_inquiries(db, skip=skip, limit=per_page, status=status)

    # Get total count
    from database import Inquiry as InquiryModel
    query = db.query(InquiryModel)
    if status:
        query = query.filter(InquiryModel.status == status)
    total = query.count()

    return {
        "inquiries": [InquiryResponse.model_validate(i) for i in inquiries],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.ENABLE_API_DOCS else "disabled",
        "health": "/health"
    }


# ========================================
# AI Agent (NVIDIA NIM)
# ========================================
# The NVIDIA API key lives only in the backend environment - it is never sent to
# the browser. The admin dashboard talks to these endpoints instead.

@app.get("/api/ai/status", tags=["AI Agent"], summary="AI Agent capability report")
async def ai_agent_status(admin=Depends(verify_admin)):
    """Report which NVIDIA models are configured, so the UI can enable/disable controls"""
    return ai_status()


@app.post("/api/ai/transcribe", tags=["AI Agent"], summary="Transcribe recorded speech")
async def ai_transcribe(
    file: UploadFile = File(...),
    admin=Depends(verify_admin)
):
    """Speech -> text via NVIDIA NIM"""
    audio = await file.read()
    text = await transcribe_audio(
        audio,
        filename=file.filename or "speech.webm",
        content_type=file.content_type or "audio/webm",
    )
    return {"text": text}


@app.post("/api/ai/chat", tags=["AI Agent"], summary="Coach reply + English correction")
async def ai_chat(payload: AIChatRequest, admin=Depends(verify_admin)):
    """Text -> corrected sentence + spoken reply via the NVIDIA chat model"""
    result = await coach_reply(payload.text, payload.history, payload.mode)
    result["mode"] = payload.mode
    return AIChatResponse(**result)


@app.post("/api/ai/speak", tags=["AI Agent"], summary="Synthesise speech")
async def ai_speak(payload: AISpeakRequest, admin=Depends(verify_admin)):
    """Text -> spoken audio. Provider-agnostic; keyless by default."""
    audio, media_type = await synthesize_speech(payload.text, payload.voice)
    return Response(content=audio, media_type=media_type)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )