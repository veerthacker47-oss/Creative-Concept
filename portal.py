"""Read-only student/parent portal plus staff-managed portal credentials."""
from functools import wraps
import secrets

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from ..db import audit, execute, get_setting, query
from ..security import (clear_login_failures, hash_password, login_rate_limited, password_error,
                        permission_required, record_login_failure, verify_password)
from ..services.fees import student_ledger
from ..utils import today_local

bp = Blueprint("portal", __name__, url_prefix="/portal")


def portal_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        account_id = session.get("portal_account_id")
        account = query(
            "SELECT pa.*, s.first_name, s.last_name, s.admission_no, s.batch_id, s.status AS student_status,"
            " b.name AS batch_name FROM portal_accounts pa JOIN students s ON s.id=pa.student_id"
            " LEFT JOIN batches b ON b.id=s.batch_id WHERE pa.id=? AND pa.active=1",
            (account_id,), one=True) if account_id else None
        if (not account or account["student_status"] != "active" or
                session.get("portal_session_version") != account["session_version"]):
            session.pop("portal_account_id", None)
            return redirect(url_for("portal.login"))
        g.portal_account = account
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    existing_id = session.get("portal_account_id")
    if existing_id:
        existing = query("SELECT session_version FROM portal_accounts WHERE id=? AND active=1", (existing_id,), one=True)
        if existing and session.get("portal_session_version") == existing["session_version"]:
            return redirect(url_for("portal.dashboard"))
    if existing_id:
        session.pop("portal_account_id", None)
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if login_rate_limited("portal:" + ip):
            flash("Too many failed attempts. Wait 15 minutes and try again.", "error")
            return render_template("portal_login.html"), 429
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        account = query("SELECT * FROM portal_accounts WHERE username=? AND active=1", (username,), one=True)
        if account and len(password) <= 1024 and verify_password(account["password_hash"], password):
            student = query("SELECT status FROM students WHERE id=?", (account["student_id"],), one=True)
            if student and student["status"] == "active":
                clear_login_failures("portal:" + ip)
                session.clear()
                session.permanent = True
                session["portal_account_id"] = account["id"]
                session["portal_session_version"] = account["session_version"]
                session["csrf"] = secrets.token_urlsafe(32)
                return redirect(url_for("portal.dashboard"))
        record_login_failure("portal:" + ip)
        flash("Invalid portal username or password.", "error")
    return render_template("portal_login.html")


@bp.route("/")
@portal_required
def dashboard():
    s = g.portal_account
    student_id = s["student_id"]
    attendance = query(
        "SELECT COUNT(*) AS total, SUM(status IN ('present','late')) AS attended,"
        " SUM(status='absent') AS absent FROM attendance WHERE student_id=?", (student_id,), one=True)
    marks = query(
        "SELECT e.name, e.subject, e.exam_date, e.max_marks, e.pass_marks, m.marks, m.absent"
        " FROM marks m JOIN exams e ON e.id=m.exam_id WHERE m.student_id=?"
        " ORDER BY COALESCE(e.exam_date, '') DESC, e.id DESC LIMIT 12", (student_id,))
    ledger = student_ledger(student_id)
    try:
        pass_pct = float(get_setting("pass_percentage", "35"))
    except (TypeError, ValueError):
        pass_pct = 35.0
    timetable = query(
        "SELECT weekday, start_time, end_time, subject, room FROM timetable WHERE batch_id=?"
        " ORDER BY weekday, start_time", (s["batch_id"],)) if s["batch_id"] else []
    homework = query(
        "SELECT title, details, due_date, created_at FROM homework WHERE batch_id=?"
        " ORDER BY COALESCE(due_date, '9999-12-31'), id DESC LIMIT 12", (s["batch_id"],)) if s["batch_id"] else []
    announcements = query(
        "SELECT title, body, created_at FROM announcements WHERE batch_id IS NULL OR batch_id=?"
        " ORDER BY id DESC LIMIT 8", (s["batch_id"],))
    return render_template("portal_dashboard.html", s=s, attendance=attendance, marks=marks,
                           ledger=ledger, timetable=timetable, homework=homework,
                           announcements=announcements, today=today_local(), pass_pct=pass_pct)


@bp.route("/password", methods=["GET", "POST"])
@portal_required
def change_password():
    account = g.portal_account
    if request.method == "POST":
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""
        error = None
        stored = query("SELECT password_hash FROM portal_accounts WHERE id=?", (account["id"],), one=True)
        if not stored or not verify_password(stored["password_hash"], current):
            error = "Current password is incorrect."
        else:
            error = password_error(new, confirm)
        if error:
            flash(error, "error")
        else:
            execute("UPDATE portal_accounts SET password_hash=?, session_version=session_version+1 WHERE id=?", (hash_password(new), account["id"]))
            updated = query("SELECT session_version FROM portal_accounts WHERE id=?", (account["id"],), one=True)
            session["portal_session_version"] = updated["session_version"]
            audit("portal.password_changed", "portal_account", account["id"], account["username"])
            flash("Password updated successfully.", "ok")
            return redirect(url_for("portal.dashboard"))
    return render_template("portal_password.html", s=account)


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("portal_account_id", None)
    session.pop("portal_session_version", None)
    session.pop("csrf", None)
    return redirect(url_for("portal.login"))


@bp.route("/accounts", methods=["GET", "POST"])
@permission_required("students.edit")
def accounts():
    if request.method == "POST":
        student_id = request.form.get("student_id", type=int)
        username = (request.form.get("username") or "").strip()[:80]
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        account_type = request.form.get("account_type", "parent")
        student = query("SELECT id, first_name, last_name, admission_no FROM students WHERE id=? AND status='active'",
                        (student_id,), one=True) if student_id else None
        errors = []
        if not student:
            errors.append("Choose an active student.")
        if not username or len(username) < 3:
            errors.append("Username must contain at least 3 characters.")
        if account_type not in ("student", "parent"):
            errors.append("Choose student or parent account type.")
        if password_error(password, confirm):
            errors.append(password_error(password, confirm))
        if username and query("SELECT 1 FROM portal_accounts WHERE username=?", (username,), one=True):
            errors.append("That portal username is already in use.")
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            aid = execute(
                "INSERT INTO portal_accounts(username, password_hash, account_type, student_id) VALUES (?,?,?,?)",
                (username, hash_password(password), account_type, student_id)).lastrowid
            audit("portal.account_created", "portal_account", aid,
                  f"{account_type} for {student['admission_no']}")
            flash(f"Portal account created for {student['first_name']}. Give the login details to the family securely.", "ok")
            return redirect(url_for("portal.accounts"))
    students = query("SELECT id, admission_no, first_name, last_name FROM students WHERE status='active' ORDER BY first_name")
    accounts = query(
        "SELECT pa.id, pa.username, pa.account_type, pa.active, pa.created_at, s.first_name, s.last_name, s.admission_no"
        " FROM portal_accounts pa JOIN students s ON s.id=pa.student_id ORDER BY pa.id DESC")
    return render_template("portal_accounts.html", students=students, accounts=accounts)


@bp.route("/accounts/<int:aid>/toggle", methods=["POST"])
@permission_required("students.edit")
def toggle_account(aid):
    account = query("SELECT active, username FROM portal_accounts WHERE id=?", (aid,), one=True)
    if account:
        active = 0 if account["active"] else 1
        execute("UPDATE portal_accounts SET active=? WHERE id=?", (active, aid))
        audit("portal.account_toggled", "portal_account", aid, f"active={active}")
        flash(f"Portal account {account['username']} {'activated' if active else 'disabled'}.", "ok")
    return redirect(url_for("portal.accounts"))
