from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import audit, execute, query
from ..security import permission_required
from ..utils import fmt_money, parse_date, parse_money

bp = Blueprint("academics", __name__, url_prefix="/batches")

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _teachers():
    return query("SELECT id, full_name FROM users WHERE role IN ('admin','teacher') AND active=1"
                 " ORDER BY full_name")


def _batch_or_404(bid):
    return query("SELECT b.*, u.full_name AS teacher_name FROM batches b"
                 " LEFT JOIN users u ON u.id=b.teacher_id WHERE b.id=?", (bid,), one=True)


def _batch_form_values(form):
    errors = []
    name = (form.get("name") or "").strip()
    if not name:
        errors.append("Batch name is required.")
    try:
        capacity = int(form.get("capacity") or 40)
        if capacity < 1:
            raise ValueError
    except ValueError:
        capacity = None
        errors.append("Capacity must be a whole number above zero.")
    fee_text = (form.get("monthly_fee") or "").strip()
    fee_paise = 0
    if fee_text:
        try:
            fee_paise = parse_money(fee_text)
        except ValueError as exc:
            errors.append(f"Monthly fee: {exc}")
    return {
        "name": name,
        "subject": (form.get("subject") or "").strip(),
        "teacher_id": form.get("teacher_id") or None,
        "capacity": capacity or 40,
        "monthly_fee_paise": fee_paise,
        "active": 1 if form.get("active", "1") == "1" else 0,
    }, errors


@bp.route("/")
@permission_required("academics.view")
def index():
    batches = query(
        "SELECT b.*, u.full_name AS teacher_name,"
        " (SELECT COUNT(*) FROM students s WHERE s.batch_id=b.id AND s.status='active') AS strength"
        " FROM batches b LEFT JOIN users u ON u.id=b.teacher_id ORDER BY b.active DESC, b.name")
    return render_template("batches.html", batches=batches, teachers=_teachers())


@bp.route("/new", methods=["POST"])
@permission_required("batches.manage")
def create():
    data, errors = _batch_form_values(request.form)
    if not errors and query("SELECT 1 FROM batches WHERE name=?", (data["name"],), one=True):
        errors.append("A batch with this name already exists.")
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("academics.index"))
    bid = execute(
        "INSERT INTO batches(name, subject, teacher_id, capacity, monthly_fee_paise, active)"
        " VALUES (?,?,?,?,?,?)",
        (data["name"], data["subject"], data["teacher_id"], data["capacity"],
         data["monthly_fee_paise"], data["active"]),
    ).lastrowid
    audit("batch.created", "batch", bid, data["name"])
    flash(f"Batch '{data['name']}' created.", "ok")
    return redirect(url_for("academics.detail", bid=bid))


@bp.route("/<int:bid>")
@permission_required("academics.view")
def detail(bid):
    batch = _batch_or_404(bid)
    if not batch:
        return render_template("error.html", code=404, message="Batch not found."), 404
    students = query("SELECT id, admission_no, first_name, last_name, status FROM students"
                     " WHERE batch_id=? ORDER BY first_name", (bid,))
    timetable = query("SELECT * FROM timetable WHERE batch_id=? ORDER BY weekday, start_time", (bid,))
    homework = query("SELECT * FROM homework WHERE batch_id=? ORDER BY COALESCE(due_date,'9999') DESC,"
                     " id DESC LIMIT 50", (bid,))
    return render_template("batch_detail.html", batch=batch, students=students,
                           timetable=timetable, homework=homework, weekdays=WEEKDAYS,
                           teachers=_teachers(), fmt_fee=fmt_money)


@bp.route("/<int:bid>/edit", methods=["POST"])
@permission_required("batches.manage")
def edit(bid):
    if not _batch_or_404(bid):
        return render_template("error.html", code=404, message="Batch not found."), 404
    data, errors = _batch_form_values(request.form)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("academics.detail", bid=bid))
    execute(
        "UPDATE batches SET name=?, subject=?, teacher_id=?, capacity=?, monthly_fee_paise=?,"
        " active=? WHERE id=?",
        (data["name"], data["subject"], data["teacher_id"], data["capacity"],
         data["monthly_fee_paise"], data["active"], bid),
    )
    audit("batch.updated", "batch", bid, data["name"])
    flash("Batch saved.", "ok")
    return redirect(url_for("academics.detail", bid=bid))


@bp.route("/<int:bid>/timetable", methods=["POST"])
@permission_required("academics.edit")
def add_timetable(bid):
    try:
        weekday = int(request.form.get("weekday", -1))
    except ValueError:
        weekday = -1
    start = (request.form.get("start_time") or "").strip()
    end = (request.form.get("end_time") or "").strip()
    subject = (request.form.get("subject") or "").strip()
    room = (request.form.get("room") or "").strip()
    if weekday not in range(7) or not start or not end or not subject:
        flash("Timetable entries need a day, start and end time, and subject.", "error")
    elif end <= start:
        flash("End time must be after start time.", "error")
    else:
        dup = query("SELECT 1 FROM timetable WHERE batch_id=? AND weekday=? AND start_time=?",
                    (bid, weekday, start), one=True)
        if dup:
            flash("A class already starts at that time on that day.", "error")
        else:
            execute("INSERT INTO timetable(batch_id, weekday, start_time, end_time, subject, room)"
                    " VALUES (?,?,?,?,?,?)", (bid, weekday, start, end, subject, room))
            audit("timetable.added", "batch", bid, f"{WEEKDAYS[weekday]} {start}")
            flash("Class added to timetable.", "ok")
    return redirect(url_for("academics.detail", bid=bid))


@bp.route("/<int:bid>/timetable/<int:tid>/delete", methods=["POST"])
@permission_required("academics.edit")
def delete_timetable(bid, tid):
    execute("DELETE FROM timetable WHERE id=? AND batch_id=?", (tid, bid))
    audit("timetable.deleted", "timetable", tid)
    flash("Class removed.", "ok")
    return redirect(url_for("academics.detail", bid=bid))


@bp.route("/<int:bid>/homework", methods=["POST"])
@permission_required("academics.edit")
def add_homework(bid):
    title = (request.form.get("title") or "").strip()
    details = (request.form.get("details") or "").strip()
    due = parse_date(request.form.get("due_date"))
    if not title:
        flash("Homework needs a title.", "error")
    else:
        hid = execute(
            "INSERT INTO homework(batch_id, title, details, due_date, created_by) VALUES (?,?,?,?,?)",
            (bid, title, details, due, session.get("user_id")),
        ).lastrowid
        audit("homework.added", "homework", hid, title)
        flash("Homework posted.", "ok")
    return redirect(url_for("academics.detail", bid=bid))


@bp.route("/homework/<int:hid>/delete", methods=["POST"])
@permission_required("academics.edit")
def delete_homework(hid):
    row = query("SELECT batch_id FROM homework WHERE id=?", (hid,), one=True)
    if row:
        execute("DELETE FROM homework WHERE id=?", (hid,))
        audit("homework.deleted", "homework", hid)
        return redirect(url_for("academics.detail", bid=row["batch_id"]))
    return redirect(url_for("academics.index"))
