from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import audit, execute, query
from ..security import ROLE_LABELS, hash_password, password_error, permission_required

bp = Blueprint("staff", __name__, url_prefix="/staff")


def _active_admins_excluding(uid):
    return query("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND active=1 AND id<>?",
                 (uid,), one=True)["n"]


@bp.route("/")
@permission_required("staff.manage")
def index():
    users = query("SELECT id, username, full_name, role, phone, designation, active, last_login"
                  " FROM users ORDER BY active DESC, full_name")
    return render_template("staff_list.html", users=users, labels=ROLE_LABELS)


@bp.route("/new", methods=["GET", "POST"])
@permission_required("staff.manage")
def new():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        full_name = (request.form.get("full_name") or "").strip()
        role = request.form.get("role", "staff")
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        error = password_error(password, confirm)
        if not username or not full_name:
            error = "Username and full name are required."
        elif role not in ROLE_LABELS:
            error = "Choose a valid role."
        elif query("SELECT 1 FROM users WHERE username=?", (username,), one=True):
            error = "That username is already taken."
        if error:
            flash(error, "error")
            return render_template("staff_form.html", member=request.form, labels=ROLE_LABELS,
                                   mode="new"), 400
        uid = execute(
            "INSERT INTO users(username, full_name, password_hash, role, phone, designation)"
            " VALUES (?,?,?,?,?,?)",
            (username, full_name, hash_password(password), role,
             (request.form.get("phone") or "").strip(), (request.form.get("designation") or "").strip()),
        ).lastrowid
        audit("staff.created", "user", uid, f"{username} ({role})")
        flash(f"Account created for {full_name}. Share the password securely.", "ok")
        return redirect(url_for("staff.index"))
    return render_template("staff_form.html", member={"role": "staff"}, labels=ROLE_LABELS, mode="new")


@bp.route("/<int:uid>/edit", methods=["GET", "POST"])
@permission_required("staff.manage")
def edit(uid):
    member = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not member:
        return render_template("error.html", code=404, message="Account not found."), 404
    if request.method == "POST":
        role = request.form.get("role", member["role"])
        active = 1 if request.form.get("active") == "1" else 0
        if role not in ROLE_LABELS:
            flash("Choose a valid role.", "error")
            return redirect(url_for("staff.edit", uid=uid))
        if uid == g.user["id"] and (not active or role != "admin"):
            flash("You cannot remove your own administrator access.", "error")
            return redirect(url_for("staff.edit", uid=uid))
        if member["role"] == "admin" and (role != "admin" or not active) \
                and _active_admins_excluding(uid) == 0:
            flash("At least one active administrator must remain.", "error")
            return redirect(url_for("staff.edit", uid=uid))
        execute("UPDATE users SET full_name=?, role=?, phone=?, designation=?, active=? WHERE id=?",
                ((request.form.get("full_name") or member["full_name"]).strip(), role,
                 (request.form.get("phone") or "").strip(),
                 (request.form.get("designation") or "").strip(), active, uid))
        audit("staff.updated", "user", uid, f"role={role} active={active}")
        flash("Account updated.", "ok")
        return redirect(url_for("staff.index"))
    return render_template("staff_form.html", member=dict(member), labels=ROLE_LABELS, mode="edit")


@bp.route("/<int:uid>/reset-password", methods=["POST"])
@permission_required("staff.manage")
def reset_password(uid):
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")
    error = password_error(password, confirm)
    if error:
        flash(error, "error")
    else:
        execute("UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?", (hash_password(password), uid))
        audit("staff.password_reset", "user", uid)
        flash("Password reset.", "ok")
    return redirect(url_for("staff.edit", uid=uid))
