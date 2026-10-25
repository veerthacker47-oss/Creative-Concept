import logging
import os

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_from_directory, url_for

from ..db import audit, create_backup, get_setting, query, set_setting
from ..security import permission_required
from ..utils import valid_email
from ..secret_storage import fernet_for_secret
from ..services.notify import mail_config, _send_email

bp = Blueprint("admin", __name__, url_prefix="/admin")

SETTING_FIELDS = {
    "institute_name": "Institute name",
    "institute_address": "Address",
    "institute_phone": "Phone",
    "institute_email": "Email",
    "pass_percentage": "Pass percentage for exams",
    "fee_due_day": "Day of month fees are due (1-28)",
    "notify_channels": "Parent channels (email, sms, whatsapp; comma separated)",
    "legal_business_name": "Legal / registered business name",
    "privacy_contact_email": "Privacy contact email",
    "privacy_contact_phone": "Privacy contact phone",
    "grievance_contact": "Grievance / privacy request contact details",
    "data_retention_policy": "Data retention schedule",
    "refund_policy_terms": "Actual refund and cancellation terms",
}


@bp.route("/settings", methods=["GET", "POST"])
@permission_required("settings.manage")
def settings():
    if request.method == "POST":
        errors = []
        values = {k: (request.form.get(k) or "").strip() for k in SETTING_FIELDS}
        try:
            pct = float(values["pass_percentage"] or 35)
            if not 0 < pct <= 100:
                raise ValueError
        except ValueError:
            errors.append("Pass percentage must be between 1 and 100.")
        try:
            due = int(values["fee_due_day"] or 10)
            if not 1 <= due <= 28:
                raise ValueError
        except ValueError:
            errors.append("Fee due day must be between 1 and 28.")
        if values["privacy_contact_email"] and not valid_email(values["privacy_contact_email"]):
            errors.append("Privacy contact email must be a valid email address.")
        if values["institute_email"] and not valid_email(values["institute_email"]):
            errors.append("Institute email must be a valid email address.")
        for key, value in values.items():
            if len(value) > (4000 if key in {"refund_policy_terms", "data_retention_policy", "grievance_contact"} else 254):
                errors.append(f"{SETTING_FIELDS[key]} is too long.")
        allowed = {"email", "sms", "whatsapp"}
        chans = [c.strip() for c in values["notify_channels"].split(",") if c.strip()]
        if any(c not in allowed for c in chans):
            errors.append("Parent channels may only contain email, sms and whatsapp.")
        if errors:
            for e in errors:
                flash(e, "error")
            return redirect(url_for("admin.settings"))
        values["pass_percentage"] = str(pct)
        values["fee_due_day"] = str(due)
        values["notify_channels"] = ",".join(chans)
        for key, value in values.items():
            set_setting(key, value)
        audit("settings.updated", "settings", None, ", ".join(SETTING_FIELDS))
        flash("Settings saved.", "ok")
        return redirect(url_for("admin.settings"))

    current = {k: get_setting(k, "") for k in SETTING_FIELDS}
    if not current["institute_name"]:
        current["institute_name"] = current_app.config["INSTITUTE_NAME"]
    if not current["pass_percentage"]:
        current["pass_percentage"] = "35"
    if not current["fee_due_day"]:
        current["fee_due_day"] = "10"
    if not current["notify_channels"]:
        current["notify_channels"] = "email,sms"
    mail = mail_config()
    providers = {
        "email": bool(mail["SMTP_HOST"] and mail["SMTP_USER"] and mail["SMTP_PASSWORD"] and (mail["SMTP_FROM"] or mail["SMTP_USER"])),
        "sms": bool(current_app.config["TWILIO_ACCOUNT_SID"] and current_app.config["TWILIO_SMS_FROM"]),
        "whatsapp": bool(current_app.config["TWILIO_ACCOUNT_SID"] and current_app.config["TWILIO_WHATSAPP_FROM"]),
        "ai": bool(current_app.config["ANTHROPIC_API_KEY"]),
    }
    email_values = {"host": mail["SMTP_HOST"], "port": mail["SMTP_PORT"],
                    "user": mail["SMTP_USER"], "sender": mail["SMTP_FROM"],
                    "has_password": bool(mail["SMTP_PASSWORD"])}
    return render_template("admin_settings.html", fields=SETTING_FIELDS, values=current,
                           providers=providers, email_values=email_values,
                           email_encryption_ready=bool(current_app.config.get("EMAIL_SETTINGS_ENCRYPTION_KEY")))


@bp.route("/email-settings", methods=["POST"])
@permission_required("settings.manage")
def email_settings():
    """Save SMTP settings; credentials are encrypted before they enter the database."""
    key = current_app.config.get("EMAIL_SETTINGS_ENCRYPTION_KEY", "")
    if not key:
        flash("Secure website-based email setup is disabled until EMAIL_SETTINGS_ENCRYPTION_KEY is configured on the server.", "error")
        return redirect(url_for("admin.settings"))
    host = (request.form.get("smtp_host") or "").strip().lower()
    port_raw = (request.form.get("smtp_port") or "587").strip()
    username = (request.form.get("smtp_user") or "").strip()
    sender = (request.form.get("smtp_from") or username).strip()
    password = request.form.get("smtp_password") or ""
    allowed_hosts = {"smtp.gmail.com", "smtp-relay.brevo.com", "smtp.office365.com"}
    errors = []
    if host not in allowed_hosts:
        errors.append("Choose a supported SMTP host: Gmail, Brevo, or Microsoft 365.")
    try:
        port = int(port_raw)
        if port not in (465, 587):
            raise ValueError
    except ValueError:
        errors.append("SMTP port must be 465 or 587.")
        port = 587
    if not valid_email(username):
        errors.append("Enter a valid sender login email address.")
    if not valid_email(sender):
        errors.append("Enter a valid From email address.")
    if len(password) > 1024:
        errors.append("The SMTP password is too long.")
    if password and not password.strip():
        errors.append("The SMTP password cannot contain only spaces.")
    existing = mail_config()
    if not password and not existing["SMTP_PASSWORD"]:
        errors.append("Enter the SMTP App Password. It will be encrypted and never shown again.")
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("admin.settings"))
    try:
        cipher = fernet_for_secret(key)
        if password:
            encrypted = cipher.encrypt(password.encode("utf-8")).decode("ascii")
            set_setting("mail_smtp_password_encrypted", encrypted)
        set_setting("mail_smtp_host", host)
        set_setting("mail_smtp_port", str(port))
        set_setting("mail_smtp_user", username)
        set_setting("mail_smtp_from", sender)
    except (ValueError, UnicodeError):
        flash("Email encryption is misconfigured. Check EMAIL_SETTINGS_ENCRYPTION_KEY on the server.", "error")
        return redirect(url_for("admin.settings"))
    audit("settings.smtp_updated", "settings", None, "SMTP configuration updated")
    flash("Email settings saved securely. Send a test email before relying on notifications.", "ok")
    return redirect(url_for("admin.settings"))


@bp.route("/email-settings/test", methods=["POST"])
@permission_required("settings.manage")
def test_email_settings():
    recipient = (request.form.get("recipient") or "").strip()
    if not valid_email(recipient):
        flash("Enter a valid test recipient email address.", "error")
        return redirect(url_for("admin.settings"))
    try:
        _send_email(recipient, "Coaching Institute SMTP test", "This is a test email from the coaching institute management system. If you received it, SMTP accepted the message.")
    except Exception:
        current_app.logger.exception("SMTP test email failed")
        flash("Test email failed. Check the SMTP host, port, sender, App Password and server logs.", "error")
        return redirect(url_for("admin.settings"))
    audit("settings.smtp_test_sent", "settings", None, "SMTP test message accepted by provider")
    flash("SMTP provider accepted the test email. This does not guarantee final inbox delivery.", "ok")
    return redirect(url_for("admin.settings"))


@bp.route("/audit")
@permission_required("audit.view")
def audit_log():
    action = request.args.get("action", "").strip()
    args, clause = [], ""
    if action:
        clause = "WHERE a.action LIKE ?"
        args.append(f"%{action}%")
    rows = query(
        f"SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id=a.user_id"
        f" {clause} ORDER BY a.id DESC LIMIT 300", args)
    return render_template("admin_audit.html", rows=rows, action=action)


@bp.route("/backups")
@permission_required("backups.manage")
def backups():
    folder = current_app.config["BACKUP_DIR"]
    files = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder), reverse=True):
            if name.startswith("institute-") and name.endswith(".db"):
                size = os.path.getsize(os.path.join(folder, name))
                files.append({"name": name, "kb": round(size / 1024, 1)})
    return render_template("admin_backups.html", files=files, folder=folder,
                           keep=current_app.config["BACKUP_KEEP"])


@bp.route("/backups/create", methods=["POST"])
@permission_required("backups.manage")
def backup_now():
    try:
        path = create_backup(current_app.config["DATABASE"], current_app.config["BACKUP_DIR"],
                             current_app.config["BACKUP_KEEP"])
    except Exception:
        current_app.logger.exception("Database backup failed")
        flash("Backup failed. Check the server logs or contact the administrator.", "error")
        return redirect(url_for("admin.backups"))
    audit("backup.created", "backup", os.path.basename(path))
    flash(f"Backup created and verified: {os.path.basename(path)}", "ok")
    return redirect(url_for("admin.backups"))


@bp.route("/backups/<name>")
@permission_required("backups.manage")
def backup_download(name):
    if "/" in name or "\\" in name or not name.startswith("institute-") or not name.endswith(".db"):
        return render_template("error.html", code=404, message="Backup not found."), 404
    audit("backup.downloaded", "backup", name)
    return send_from_directory(current_app.config["BACKUP_DIR"], name, as_attachment=True)
