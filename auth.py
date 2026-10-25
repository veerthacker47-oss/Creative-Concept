from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for

from ..db import audit, execute, query
from ..security import (
    clear_login_failures, hash_password, login_required, login_rate_limited,
    password_error, record_login_failure, verify_password,
)

bp = Blueprint("auth", __name__)


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First-run only: create the initial administrator. Disabled once any user exists."""
    if query("SELECT COUNT(*) AS n FROM users", one=True)["n"] > 0:
        return redirect(url_for("auth.login"))
    setup_token = current_app.config.get("INITIAL_SETUP_TOKEN", "")
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        setup_bucket = "setup:" + ip
        if login_rate_limited(setup_bucket):
            flash("Too many setup attempts. Wait 15 minutes before trying again.", "error")
            return render_template("setup.html", token_required=bool(setup_token)), 429
        if setup_token:
            supplied = request.form.get("setup_token", "")
            if not __import__("hmac").compare_digest(supplied, setup_token):
                record_login_failure(setup_bucket)
                flash("The one-time setup token is invalid.", "error")
                return render_template("setup.html", token_required=True), 403
        clear_login_failures(setup_bucket)
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        error = password_error(password, confirm)
        if not username or not full_name:
            error = "Username and full name are required."
        if error:
            flash(error, "error")
            return render_template("setup.html", token_required=bool(setup_token)), 400
        created = execute(
            "INSERT INTO users(username, full_name, password_hash, role) "
            "SELECT ?, ?, ?, 'admin' WHERE NOT EXISTS (SELECT 1 FROM users)",
            (username, full_name, hash_password(password)),
        )
        if created.rowcount != 1:
            flash("Administrator setup has already been completed. Please sign in.", "error")
            return redirect(url_for("auth.login"))
        uid = created.lastrowid
        session.clear()
        session["user_id"] = uid
        session["session_version"] = 0
        session.permanent = True
        audit("setup.admin_created", "user", uid, username)
        flash("Administrator account created. Set your institute details in Settings.", "ok")
        return redirect(url_for("admin.settings"))
    return render_template("setup.html", token_required=bool(setup_token))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if login_rate_limited(ip):
            flash("Too many failed attempts. Wait 15 minutes and try again.", "error")
            return render_template("login.html"), 429
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = query("SELECT * FROM users WHERE username=? AND active=1", (username,), one=True)
        if user and len(password) <= 1024 and verify_password(user["password_hash"], password):
            clear_login_failures(ip)
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["session_version"] = user["session_version"]
            execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user["id"],))
            audit("auth.login", "user", user["id"])
            return redirect(_safe_next(request.args.get("next")) or url_for("dashboard.index"))
        record_login_failure(ip)
        flash("Invalid username or password.", "error")
        return render_template("login.html"), 401
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    if g.get("user"):
        audit("auth.logout", "user", g.user["id"])
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        current = request.form.get("current", "")
        new = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not verify_password(g.user["password_hash"], current):
            flash("Your current password is incorrect.", "error")
        elif password_error(new, confirm):
            flash(password_error(new, confirm), "error")
        else:
            execute("UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?",
                    (hash_password(new), g.user["id"]))
            updated = query("SELECT session_version FROM users WHERE id=?", (g.user["id"],), one=True)
            session["session_version"] = updated["session_version"]
            audit("auth.password_changed", "user", g.user["id"])
            flash("Password changed.", "ok")
            return redirect(url_for("auth.account"))
    return render_template("account.html")
