"""
Configuration settings for A2M Digital Solutions Backend
"""
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "A2M Digital Solutions API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS - Update with your frontend domain in production
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5500",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5500",
        "http://127.0.0.1:8000",
        "https://a2mdigitalsolutions.com",  # Update with your domain
        "https://www.a2mdigitalsolutions.com",
    ]

    # Database (SQLite - zero cost)
    DATABASE_URL: str = "sqlite:///./inquiries.db"

    # Email Configuration
    # Choose one: Gmail, SendGrid, Brevo, Mailgun, etc.
    EMAIL_PROVIDER: str = "gmail"  # gmail, sendgrid, brevo, mailgun, custom

    # SMTP Settings (used for gmail, brevo, mailgun, custom)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""  # App password for Gmail
    SMTP_USE_TLS: bool = True

    # SendGrid API (if using SendGrid)
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = ""

    # Email addresses
    FROM_EMAIL: str = "info@a2mdigitalsolutions.com"
    FROM_NAME: str = "A2M Digital Solutions"
    TO_EMAIL: str = "info@a2mdigitalsolutions.com"  # Where inquiries are sent

    # Rate limiting (requests per minute per IP)
    RATE_LIMIT: int = 10

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()