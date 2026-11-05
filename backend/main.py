"""
A2M Digital Solutions - FastAPI Backend
Handles inquiry form submissions, email notifications, admin dashboard, and visitor tracking
"""
from contextlib import asynccontextmanager
from typing import Optional, List
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, HTTPException, status, Response, Cookie
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
    get_visitor_stats, get_admin_user, create_admin_user, update_last_login,
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
    VisitorStats
)
from email_service import send_inquiry_email

settings = get_settings()

security = HTTPBasic()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password


def hash_password(password: str) -> str:
    """Hash a password"""
    return hashlib.sha256(password.encode()).hexdigest()


def create_access_token() -> str:
    """Create a simple session token"""
    return secrets.token_urlsafe(32)


def verify_admin(credentials: HTTPBasicCredentials = Depends(security), db: Session = Depends(get_db)):
    """Verify admin credentials"""
    admin = get_admin_user(db, credentials.username)
    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    if not verify_password(credentials.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    init_db()

    # Create default admin if not exists
    db = next(get_db())
    admin = get_admin_user(db, "admin")
    if not admin:
        create_admin_user(db, "admin", hash_password("admin123"))
        print("Created default admin user: admin / admin123")
    db.close()

    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"📧 Email provider: {settings.EMAIL_PROVIDER}")
    print(f"🗄️  Database: {settings.DATABASE_URL}")
    yield
    # Shutdown
    print("👋 Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for A2M Digital Solutions inquiry form with admin dashboard",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
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
    """Track visitor count"""
    # Skip tracking for static files, API docs, health checks
    skip_paths = ["/docs", "/redoc", "/openapi.json", "/health", "/favicon.ico", "/robots.txt"]
    if any(request.url.path.startswith(path) for path in skip_paths):
        return await call_next(request)

    # Track visitor
    db = next(get_db())
    try:
        # Simple unique visitor detection via IP (in production, use cookies/session)
        client_ip = request.client.host
        # For simplicity, we'll count all requests as visits
        # In production, use cookies/sessions for unique visitors
        increment_visitor_count(db, is_unique=False)
    except Exception as e:
        print(f"Visitor tracking error: {e}")
    finally:
        db.close()

    response = await call_next(request)
    return response


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


# Visitor Stats (Public)
@app.get("/api/visitors", response_model=VisitorStats, tags=["Visitors"])
async def get_visitor_stats_endpoint(db: Session = Depends(get_db)):
    """Get visitor statistics"""
    stats = get_visitor_stats(db)
    return VisitorStats(**stats)


# Admin Login
@app.post("/admin/login", response_model=AdminToken, tags=["Admin"])
async def admin_login(credentials: AdminLogin, response: Response, db: Session = Depends(get_db)):
    """Admin login"""
    admin = get_admin_user(db, credentials.username)
    if not admin or not admin.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(credentials.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create session token
    token = create_access_token()

    # Update last login
    update_last_login(db, admin.id)

    # Set cookie
    response.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400  # 24 hours
    )

    return AdminToken(access_token=token)


@app.post("/admin/logout", tags=["Admin"])
async def admin_logout(response: Response):
    """Admin logout"""
    response.delete_cookie(key="admin_token")
    return {"message": "Logged out successfully"}


# Admin Dashboard Stats
@app.get("/admin/stats", tags=["Admin"])
async def admin_stats(db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    """Get dashboard statistics"""
    inquiry_stats = get_inquiry_stats(db)
    visitor_stats = get_visitor_stats(next(get_db()))
    return {
        "inquiries": inquiry_stats,
        "visitors": visitor_stats
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
        "docs": "/docs" if settings.DEBUG else "disabled",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )