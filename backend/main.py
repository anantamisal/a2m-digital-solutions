"""
A2M Digital Solutions - FastAPI Backend
Handles inquiry form submissions, email notifications, and data storage
"""
from contextlib import asynccontextmanager
from typing import Optional
import asyncio
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import uvicorn

from config import get_settings
from database import init_db, get_db, create_inquiry, get_inquiries, get_inquiry, update_inquiry_status, get_inquiry_stats
from models import (
    InquiryCreate,
    InquiryResponse,
    InquiryListResponse,
    InquiryStatusUpdate,
    StatsResponse,
    HealthResponse,
    ErrorResponse
)
from email_service import send_inquiry_email

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    init_db()
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} started")
    print(f"📧 Email provider: {settings.EMAIL_PROVIDER}")
    print(f"🗄️  Database: {settings.DATABASE_URL}")
    yield
    # Shutdown
    print("👋 Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for A2M Digital Solutions inquiry form",
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


# Rate limiting middleware (simple in-memory)
request_counts = {}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Simple rate limiting by IP"""
    # Skip rate limiting for OPTIONS (CORS preflight) and health checks
    if request.method == "OPTIONS" or request.url.path == "/health":
        return await call_next(request)

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

    - **name**: Client's full name (required)
    - **email**: Client's email address (required)
    - **phone**: Phone number (optional)
    - **service**: Service interested in (required)
    - **budget**: Budget range (optional)
    - **timeline**: Expected timeline (optional)
    - **message**: Project details (required, min 10 chars)
    """
    # Prepare data for database
    inquiry_data = inquiry.model_dump()
    inquiry_data["ip_address"] = request.client.host
    inquiry_data["user_agent"] = request.headers.get("user-agent", "")

    # Create in database
    db_inquiry = create_inquiry(db, inquiry_data)

    # Send email notification (async, non-blocking)
    email_data = {
        "name": inquiry.name,
        "email": inquiry.email,
        "phone": inquiry.phone,
        "service": inquiry.service,
        "budget": inquiry.budget,
        "timeline": inquiry.timeline,
        "message": inquiry.message
    }

    # Send email in background
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
    db: Session = Depends(get_db)
):
    """
    List all inquiries with pagination and optional status filter.
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
async def get_inquiry_by_id(inquiry_id: int, db: Session = Depends(get_db)):
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
    db: Session = Depends(get_db)
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
async def get_stats(db: Session = Depends(get_db)):
    """Get inquiry statistics"""
    stats = get_inquiry_stats(db)
    return StatsResponse(**stats)


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
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )