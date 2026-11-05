"""
Pydantic models for request/response validation
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# Request Models
class InquiryCreate(BaseModel):
    """Inquiry creation request"""
    name: str = Field(..., min_length=1, max_length=255, description="Full name")
    email: EmailStr = Field(..., description="Email address")
    phone: Optional[str] = Field(None, max_length=50, description="Phone number")
    service: str = Field(..., description="Service interested in")
    timeline: Optional[str] = Field(None, description="Expected timeline")
    message: str = Field(..., min_length=10, max_length=5000, description="Project details")

    @field_validator("service")
    @classmethod
    def validate_service(cls, v):
        allowed_services = [
            "web-development",
            "mobile-app",
            "backend",
            "ui-ux",
            "devops",
            "consultation",
            "ai-agent",
            "other"
        ]
        if v not in allowed_services:
            raise ValueError(f"Service must be one of: {', '.join(allowed_services)}")
        return v

    @field_validator("timeline")
    @classmethod
    def validate_timeline(cls, v):
        if v is None:
            return v
        allowed_timelines = [
            "asap",
            "1-2-months",
            "3-6-months",
            "6-months-plus",
            "flexible"
        ]
        if v not in allowed_timelines:
            raise ValueError(f"Timeline must be one of: {', '.join(allowed_timelines)}")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is None or v.strip() == "":
            return None
        # Basic phone validation - allow various formats
        import re
        cleaned = re.sub(r'[\s\-\(\)\+]', '', v)
        if not cleaned.isdigit() or len(cleaned) < 7 or len(cleaned) > 15:
            raise ValueError("Invalid phone number format")
        return v


# Response Models
class InquiryResponse(BaseModel):
    """Inquiry response"""
    id: int
    name: str
    email: str
    phone: Optional[str]
    service: str
    timeline: Optional[str]
    message: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InquiryListResponse(BaseModel):
    """Paginated inquiry list response"""
    inquiries: list[InquiryResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class InquiryStatusUpdate(BaseModel):
    """Inquiry status update request"""
    status: str = Field(..., pattern="^(new|contacted|closed)$")


class StatsResponse(BaseModel):
    """Inquiry statistics"""
    total: int
    new: int
    contacted: int
    closed: int


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    app_name: str
    version: str
    environment: str


class ErrorResponse(BaseModel):
    """Error response"""
    detail: str
    error_code: Optional[str] = None


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VisitorStats(BaseModel):
    total_visits: int
    today_visits: int
    unique_visitors: int


# Service labels for email formatting
SERVICE_LABELS = {
    "web-development": "Web Development",
    "mobile-app": "Mobile App Development",
    "backend": "Backend Development",
    "ui-ux": "UI/UX Design",
    "devops": "DevOps & Maintenance",
    "consultation": "Consultation & Strategy",
    "ai-agent": "AI Agent Development",
    "other": "Other"
}

TIMELINE_LABELS = {
    "asap": "ASAP",
    "1-2-months": "1-2 Months",
    "3-6-months": "3-6 Months",
    "6-months-plus": "6+ Months",
    "flexible": "Flexible"
}


def get_service_label(service: str) -> str:
    return SERVICE_LABELS.get(service, service)


def get_timeline_label(timeline: Optional[str]) -> str:
    if not timeline:
        return "Not specified"
    return TIMELINE_LABELS.get(timeline, timeline)