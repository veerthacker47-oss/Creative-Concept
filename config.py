"""Application configuration. Everything secret comes from environment variables."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# Load environment settings for both Flask CLI and WSGI/Gunicorn launches.
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))


def _env_bool(name, default):
    fallback = "1" if default else "0"
    return os.environ.get(name, fallback).strip().lower() in ("1", "true", "yes", "on")


def load_secret_key():
    """Use SECRET_KEY from the environment; otherwise create one once and store it in DATA_DIR."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
    path = DATA_DIR / "secret_key.txt"
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


class Config:
    SECRET_KEY = load_secret_key()
    INSTITUTE_NAME = os.environ.get("INSTITUTE_NAME", "Creative Concept")
    TIMEZONE = os.environ.get("TIMEZONE", "Asia/Kolkata")
    DATABASE = os.environ.get("DATABASE_PATH", str(DATA_DIR / "institute.db"))
    BACKUP_DIR = os.environ.get("BACKUP_DIR", str(DATA_DIR / "backups"))
    BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "30"))

    # Set SCHEDULER_ENABLED=0 if you run `flask run-jobs` from a cron job instead.
    SCHEDULER_ENABLED = _env_bool("SCHEDULER_ENABLED", True)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Keep this on in production (HTTPS). Set COOKIE_SECURE=0 only for plain-http local testing.
    SESSION_COOKIE_SECURE = _env_bool("COOKIE_SECURE", True)
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # Email (free option: Gmail SMTP with an App Password, or Brevo's free tier)
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "")
    EMAIL_SETTINGS_ENCRYPTION_KEY = os.environ.get("EMAIL_SETTINGS_ENCRYPTION_KEY", "")
    INITIAL_SETUP_TOKEN = os.environ.get("INITIAL_SETUP_TOKEN", "")

    # SMS / WhatsApp via Twilio (paid per message; trial accounts are free but limited)
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_SMS_FROM = os.environ.get("TWILIO_SMS_FROM", "")
    TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")

    # AI assistant (optional, paid API). Without a key the assistant uses built-in commands only.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")
