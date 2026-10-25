"""Notification queue, duplicate prevention and real provider delivery.

A message is only marked 'sent' when the provider (SMTP / Twilio) accepts it.
If a provider is not configured, the message stays 'queued' with an explanation,
so nothing is ever reported as delivered when it was not.
"""
import base64
import json
import smtplib
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

from flask import current_app
from cryptography.fernet import InvalidToken

from ..db import execute, get_setting, query
from ..secret_storage import fernet_for_secret
from ..utils import normalize_phone, valid_email

MAX_ATTEMPTS = 5
CHANNELS = ("email", "sms", "whatsapp")


class NotConfigured(Exception):
    pass


def mail_config():
    """Return SMTP settings, preferring encrypted administrator settings over environment values."""
    cfg = current_app.config
    values = {
        "SMTP_HOST": cfg.get("SMTP_HOST", ""),
        "SMTP_PORT": cfg.get("SMTP_PORT", 587),
        "SMTP_USER": cfg.get("SMTP_USER", ""),
        "SMTP_PASSWORD": cfg.get("SMTP_PASSWORD", ""),
        "SMTP_FROM": cfg.get("SMTP_FROM", ""),
    }
    for field in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_FROM"):
        saved = get_setting("mail_" + field.lower(), "")
        if saved:
            values[field] = int(saved) if field == "SMTP_PORT" else saved
    encrypted = get_setting("mail_smtp_password_encrypted", "")
    if encrypted:
        key = cfg.get("EMAIL_SETTINGS_ENCRYPTION_KEY", "")
        if not key:
            values["SMTP_PASSWORD"] = ""
        else:
            try:
                values["SMTP_PASSWORD"] = fernet_for_secret(key).decrypt(encrypted.encode("ascii")).decode("utf-8")
            except (ValueError, UnicodeError, InvalidToken):
                current_app.logger.error("Saved SMTP password could not be decrypted; check EMAIL_SETTINGS_ENCRYPTION_KEY.")
                values["SMTP_PASSWORD"] = ""
    return values


def enqueue(student_id, channel, recipient, kind, body, dedupe_key, subject=None):
    """Insert a queued message. Returns True if new, False if this exact message was already queued/sent."""
    cur = execute(
        "INSERT OR IGNORE INTO notifications"
        "(student_id, channel, recipient, kind, subject, body, status, dedupe_key)"
        " VALUES (?,?,?,?,?,?,'queued',?)",
        (student_id, channel, recipient, kind, subject, body, dedupe_key),
    )
    return cur.rowcount == 1


def parent_channels(student):
    """Which channels can reach this student's parent, based on institute settings and contact details."""
    wanted = [c.strip() for c in get_setting("notify_channels", "email,sms").split(",") if c.strip()]
    result = []
    for channel in wanted:
        if channel == "email" and valid_email(student["parent_email"] or ""):
            result.append(("email", student["parent_email"]))
        elif channel in ("sms", "whatsapp") and normalize_phone(student["parent_phone"] or ""):
            result.append((channel, normalize_phone(student["parent_phone"])))
    return result


def _send_email(to, subject, body):
    cfg = current_app.config
    mail = mail_config()
    host = mail["SMTP_HOST"]
    if not host:
        raise NotConfigured("Email (SMTP) is not configured on the server.")
    sender = mail["SMTP_FROM"] or mail["SMTP_USER"]
    if not sender:
        raise NotConfigured("Email is missing a sender address: set SMTP_FROM in .env.")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject or "Message from " + cfg["INSTITUTE_NAME"]
    msg.set_content(body)
    port = int(mail["SMTP_PORT"])
    # Port 465 uses implicit SSL; 587 (and most others) use STARTTLS.
    if port == 465:
        smtp_cls = smtplib.SMTP_SSL
        conn = smtp_cls(host, port, timeout=20)
    else:
        conn = smtplib.SMTP(host, port, timeout=20)
    with conn as smtp:
        if port != 465:
            smtp.starttls()
        if mail["SMTP_USER"]:
            if not mail["SMTP_PASSWORD"]:
                raise NotConfigured("Email sender password is not configured. Save an App Password in Admin Settings.")
            smtp.login(mail["SMTP_USER"], mail["SMTP_PASSWORD"])
        smtp.send_message(msg)
    return None


def _send_twilio(to, body, whatsapp):
    sid = current_app.config["TWILIO_ACCOUNT_SID"]
    token = current_app.config["TWILIO_AUTH_TOKEN"]
    sender = current_app.config["TWILIO_WHATSAPP_FROM" if whatsapp else "TWILIO_SMS_FROM"]
    if not (sid and token and sender):
        raise NotConfigured(
            "WhatsApp (Twilio) is not configured on the server."
            if whatsapp else "SMS (Twilio) is not configured on the server."
        )
    if whatsapp:
        to, sender = f"whatsapp:{to}", f"whatsapp:{sender}"
    data = urllib.parse.urlencode({"To": to, "From": sender, "Body": body}).encode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data, method="POST"
    )
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Twilio rejected the message ({exc.code}): {detail}")
    return payload.get("sid")


def dispatch(row):
    """Send one notification row. Returns the provider id (or None). Raises on failure."""
    channel = row["channel"]
    if not row["recipient"]:
        raise ValueError("No recipient address on file.")
    if channel == "email":
        return _send_email(row["recipient"], row["subject"], row["body"])
    if channel == "sms":
        return _send_twilio(row["recipient"], row["body"], whatsapp=False)
    if channel == "whatsapp":
        return _send_twilio(row["recipient"], row["body"], whatsapp=True)
    raise ValueError(f"Unknown channel {channel}")


def send_queued(limit=200):
    """Attempt delivery of queued notifications. Returns a dict of counts."""
    counts = {"sent": 0, "failed": 0, "waiting": 0}
    rows = query(
        "SELECT * FROM notifications WHERE status='queued' ORDER BY id LIMIT ?", (limit,)
    )
    for row in rows:
        try:
            provider_id = dispatch(row)
        except NotConfigured as exc:
            execute("UPDATE notifications SET error=? WHERE id=?", (str(exc), row["id"]))
            counts["waiting"] += 1
            continue
        except ValueError as exc:
            execute(
                "UPDATE notifications SET status='failed', attempts=attempts+1, error=? WHERE id=?",
                (str(exc), row["id"]),
            )
            counts["failed"] += 1
            continue
        except Exception as exc:  # network / provider errors: retry later
            attempts = row["attempts"] + 1
            status = "failed" if attempts >= MAX_ATTEMPTS else "queued"
            execute(
                "UPDATE notifications SET attempts=?, status=?, error=? WHERE id=?",
                (attempts, status, str(exc)[:300], row["id"]),
            )
            counts["failed" if status == "failed" else "waiting"] += 1
            continue
        execute(
            "UPDATE notifications SET status='sent', attempts=attempts+1, error=NULL,"
            " provider_id=?, sent_at=datetime('now') WHERE id=?",
            (provider_id, row["id"]),
        )
        counts["sent"] += 1
    return counts


def retry_failed():
    """Reset failed messages (not for bad recipients) so they are tried again."""
    cur = execute(
        "UPDATE notifications SET status='queued', attempts=0 WHERE status='failed'"
        " AND error NOT LIKE 'No recipient%'"
    )
    return cur.rowcount
