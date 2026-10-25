"""Authentication, roles/permissions, CSRF protection and login throttling."""
import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query

PERMISSIONS = (
    "students.view", "students.edit", "attendance.mark", "attendance.view",
    "fees.view", "fees.edit", "comms.send", "academics.view", "academics.edit",
    "reports.view", "import.run", "batches.manage", "staff.manage",
    "settings.manage", "audit.view", "backups.manage", "assistant.use",
)

ROLE_PERMISSIONS = {
    "admin": set(PERMISSIONS),
    "staff": {
        "students.view", "students.edit", "attendance.mark", "attendance.view",
        "fees.view", "comms.send", "academics.view", "reports.view",
        "import.run", "assistant.use",
    },
    "teacher": {
        "students.view", "attendance.mark", "attendance.view", "academics.view",
        "academics.edit", "reports.view", "assistant.use",
    },
    "accountant": {
        "students.view", "fees.view", "reports.view", "assistant.use",
    },
}

ROLE_LABELS = {
    "admin": "Owner / Administrator",
    "staff": "Front office",
    "teacher": "Teacher",
    "accountant": "Accountant",
}

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 1024
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 8
_login_failures = defaultdict(deque)


def hash_password(password):
    return generate_password_hash(password)


def verify_password(stored_hash, password):
    return check_password_hash(stored_hash, password)


def password_error(password, confirm):
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be no longer than {MAX_PASSWORD_LENGTH} characters."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    if password != confirm:
        return "The two passwords do not match."
    return None


def load_current_user():
    g.user = None
    uid = session.get("user_id")
    if uid:
        user = query("SELECT * FROM users WHERE id=? AND active=1", (uid,), one=True)
        if user and session.get("session_version") == user["session_version"]:
            g.user = user
        elif user:
            session.clear()
        else:
            session.clear()


def has_perm(perm):
    user = g.get("user")
    return user is not None and perm in ROLE_PERMISSIONS.get(user["role"], ())


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def permission_required(*perms):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.get("user"):
                return redirect(url_for("auth.login", next=request.path))
            if not all(has_perm(p) for p in perms):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        expected = session.get("csrf") or ""
        if not expected or not sent or not secrets.compare_digest(sent, expected):
            abort(400, description="Your form expired. Reload the page and try again.")


def _rate_limit_bucket(value):
    """Pseudonymise rate-limit keys so raw IP addresses/usernames are not stored."""
    secret = str(current_app.config.get("SECRET_KEY", "local-only")).encode("utf-8")
    return hmac.new(secret, str(value).encode("utf-8"), hashlib.sha256).hexdigest()


def login_rate_limited(ip):
    """Persistent, multi-worker-safe throttle stored in SQLite, not process memory."""
    now = int(time.time())
    bucket = _rate_limit_bucket(ip)
    row = query(
        "SELECT COUNT(*) AS n FROM auth_attempts WHERE bucket_hash=? AND attempted_at>=?",
        (bucket, now - LOGIN_WINDOW_SECONDS), one=True,
    )
    return bool(row and row["n"] >= LOGIN_MAX_FAILURES)


def record_login_failure(ip):
    now = int(time.time())
    # Periodic cleanup prevents this small security table growing forever.
    execute("DELETE FROM auth_attempts WHERE attempted_at<?", (now - 24 * 60 * 60,))
    execute("INSERT INTO auth_attempts(bucket_hash, attempted_at) VALUES (?,?)",
            (_rate_limit_bucket(ip), now))


def clear_login_failures(ip):
    _login_failures.pop(ip, None)  # compatibility for older test helpers
    execute("DELETE FROM auth_attempts WHERE bucket_hash=?", (_rate_limit_bucket(ip),))
