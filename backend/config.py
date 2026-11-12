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

    # ========================================
    # Admin Authentication
    # ========================================
    # These credentials bootstrap/replace the admin user at startup.
    # CHANGE THEM IN .env - the defaults below are public knowledge.
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"

    # How long an admin session cookie stays valid (hours)
    ADMIN_SESSION_HOURS: int = 24

    # Set the session cookie as Secure (requires HTTPS).
    # Keep False for local http:// development, set True in production.
    COOKIE_SECURE: bool = False

    # ========================================
    # AI Agent - provider configuration
    # ========================================
    # The AI Agent works with NO API key on the default settings.
    # Each stage (STT / LLM / TTS) walks a chain of providers and falls
    # back to the next one when the current one is missing or fails.
    # Keys are read by the backend and NEVER sent to the browser.

    # --- Provider chains (comma separated, tried left to right) ---
    # NVIDIA has NO speech-to-text or text-to-speech models at all (its
    # catalog of 84 models contains no ASR/TTS entry and its /v1/audio/*
    # routes are not served), so it is deliberately absent from the STT and
    # TTS chains. Leaving it there only produced a doomed request and a
    # confusing error before the browser fallback kicked in.
    LLM_PROVIDER_ORDER: str = "nvidia,pollinations,groq"
    STT_PROVIDER_ORDER: str = "groq"
    TTS_PROVIDER_ORDER: str = "edge"

    # --- Pollinations: keyless LLM, no signup required ---
    POLLINATIONS_BASE_URL: str = "https://text.pollinations.ai/openai"
    POLLINATIONS_MODEL: str = "openai-fast"

    # --- Groq: free tier, one key covers both LLM and Whisper STT ---
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_API_KEY: str = ""
    GROQ_LLM_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_STT_MODEL: str = "whisper-large-v3-turbo"

    # --- Microsoft Edge TTS: keyless speech synthesis ---
    EDGE_TTS_VOICE: str = "en-US-AriaNeural"

    # --- NVIDIA NIM: optional, server-side only ---
    # NVIDIA is an LLM provider ONLY. Verified against the live catalog:
    #   - nvidia/parakeet-ctc-0.6b-asr  -> not in the catalog, /v1/audio/*
    #                                    -> 404, so NVIDIA cannot do STT
    #   - nvidia/parakeet-tts-0.6b-v2   -> not in the catalog, same
    # Model availability is PER ACCOUNT: a model listed in the catalog can
    # still return "Function not found for account ..." on a given key.
    # The default below was verified to answer on the owner's own key.
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_STT_MODEL: str = "nvidia/parakeet-ctc-0.6b-asr"
    NVIDIA_LLM_MODEL: str = "nvidia/nemotron-3.5-bolt-e4b"
    NVIDIA_TTS_MODEL: str = "nvidia/parakeet-tts-0.6b-v2"
    NVIDIA_TTS_VOICE: str = "Magdellene"
    NVIDIA_TIMEOUT: int = 90
    # Token budget for the Nemotron reasoning models. Measured on the
    # owner's own key with the real coach prompt:
    #   nvidia/nemotron-3.5-bolt-e4b            mt=600  -> 1.6-1.9 s, valid JSON
    #   nvidia/nemotron-3-nano-omni-30b-a3b-reasoning mt=1200 -> 5.7-8.5 s, valid JSON
    #   nvidia/nemotron-3.5-lightning-30b-a3b   mt=1200 -> 55 s and STILL empty
    # The reasoning models spend part of the budget thinking out loud and
    # return content: null when the budget is too small, so this must stay
    # above the reasoning overhead - but a bigger budget also means a
    # slower answer, so do not simply max it out.
    NVIDIA_MAX_TOKENS: int = 600

    # Rate limiting (requests per minute per IP)
    RATE_LIMIT: int = 10

    # Serve the interactive API documentation at /docs and /redoc.
    # The deployment scripts link to https://a2mdigitalsolutions.com/docs
    ENABLE_API_DOCS: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()