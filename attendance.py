from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from ..db import audit, execute, get_setting, query
from ..security import has_perm, permission_required
from ..services import notify
from ..utils import csv_response, parse_date, today_local

bp = Blueprint("attendance", __name__, url_prefix="/attendance")

STATUSES = ("present", "absent", "late", "excused")


def _absence_text(student, batch_name, day):
    return (
        f"Dear {student['parent_name']}, {student['first_name']} ({student['admission_no']}) "
        f"was marked ABSENT from {batch_name} on {day}. If this is unexpected, please contact "
        f"us. - {get_setting('institute_name', 'The Institute')}"
    )


def _queue_absence_alerts(student, batch_name, day):
    """Queue one alert per parent channel per student per day. Duplicates are blocked by dedupe_key."""
    queued = 0
    for channel, recipient in notify.parent_channels(student):
        if notify.enqueue(student["id"], channel, recipient, "absence", _absence_text(student, batch_name, day),
                          f"absence:{student['id']}:{day}:{channel}",
                          subject=f"{student['first_name']} was absent on {day}"):
            queued += 1
    return queued


@bp.route("/", methods=["GET", "POST"])
@permission_required("attendance.view")
def index():
    batches = query("SELECT id, name FROM batches WHERE active=1 ORDER BY name")
    batch_id = request.values.get("batch_id", type=int) or (batches[0]["id"] if batches else None)
    day = parse_date(request.values.get("date")) or today_local()
    batch = query("SELECT * FROM batches WHERE id=?", (batch_id,), one=True) if batch_id else None
    students = query(
        "SELECT * FROM students WHERE batch_id=? AND status='active' ORDER BY first_name, last_name",
        (batch_id,)) if batch else []

    if request.method == "POST":
        # Viewing is not enough to change records: saving needs the attendance.mark permission.
        if not has_perm("attendance.mark"):
            abort(403)
        if not batch:
            flash("Choose a batch first.", "error")
            return redirect(url_for("attendance.index"))
        action = request.form.get("action", "save")
        # The form sends a marker field, so an unticked checkbox (absent field) means "do not notify".
        # Requests without the marker keep the original behaviour: alerts on.
        if "notify_form" in request.form:
            notify_absent = request.form.get("notify_absent") == "1"
        else:
            notify_absent = True
        existing = {r["student_id"]: r["status"] for r in query(
            "SELECT student_id, status FROM attendance WHERE att_date=? AND batch_id=?",
            (day, batch_id))}
        new_absent = 0
        saved = 0
        for s in students:
            chosen = request.form.get(f"status_{s['id']}", "")
            if action == "mark_all_present":
                chosen = "present"                      # overrides every student in the batch
            elif chosen not in STATUSES:
                if action == "all_present" and s["id"] not in existing:
                    chosen = "present"                  # only fills students who are not marked yet
                else:
                    continue
            previous = existing.get(s["id"])
            if previous == chosen:
                continue
            execute(
                "INSERT INTO attendance(student_id, batch_id, att_date, status, marked_by)"
                " VALUES (?,?,?,?,?) ON CONFLICT(student_id, att_date) DO UPDATE SET"
                " status=excluded.status, batch_id=excluded.batch_id,"
                " marked_by=excluded.marked_by, updated_at=datetime('now')",
                (s["id"], batch_id, day, chosen, session.get("user_id")),
            )
            saved += 1
            if chosen == "absent" and notify_absent:
                new_absent += _queue_absence_alerts(s, batch["name"], day)
        audit("attendance.saved", "batch", batch_id, f"{day}: {saved} changes")
        counts = notify.send_queued() if new_absent else {"sent": 0, "waiting": 0, "failed": 0}
        msg = f"Attendance saved for {saved} student(s)."
        if new_absent:
            msg += (f" Absence alerts: {counts['sent']} sent, {counts['waiting']} waiting"
                    f" (provider not set up), {counts['failed']} failed.")
        flash(msg, "ok")
        return redirect(url_for("attendance.index", batch_id=batch_id, date=day))

    marks = {r["student_id"]: r["status"] for r in query(
        "SELECT student_id, status FROM attendance WHERE att_date=? AND batch_id=?",
        (day, batch_id))} if batch else {}
    counts = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    for st in marks.values():
        counts[st] = counts.get(st, 0) + 1
    return render_template("attendance.html", batches=batches, batch=batch, batch_id=batch_id,
                           day=day, students=students, marks=marks, statuses=STATUSES,
                           counts=counts, can_mark=has_perm("attendance.mark"))


@bp.route("/report")
@permission_required("attendance.view")
def report():
    batches = query("SELECT id, name FROM batches ORDER BY name")
    batch_id = request.args.get("batch_id", type=int)
    month = request.args.get("month") or today_local()[:7]
    day = parse_date(request.args.get("date"))
    rows, daily = [], []
    if batch_id:
        rows = query(
            "SELECT s.id, s.admission_no, s.first_name, s.last_name,"
            " COUNT(a.id) AS days,"
            " SUM(a.status IN ('present','late')) AS attended,"
            " SUM(a.status='absent') AS absent"
            " FROM students s LEFT JOIN attendance a ON a.student_id=s.id"
            " AND a.att_date LIKE ? AND a.batch_id=? WHERE s.batch_id=? AND s.status='active'"
            " GROUP BY s.id ORDER BY s.first_name",
            (f"{month}%", batch_id, batch_id))
        if day:
            daily = query(
                "SELECT s.admission_no, s.first_name, s.last_name, a.status"
                " FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.att_date=?"
                " WHERE s.batch_id=? AND s.status='active' ORDER BY s.first_name",
                (day, batch_id))
    if request.args.get("format") == "csv" and rows:
        data = [(r["admission_no"], f"{r['first_name']} {r['last_name'] or ''}".strip(),
                 r["days"], r["attended"] or 0, r["absent"] or 0,
                 round(100 * (r["attended"] or 0) / r["days"], 1) if r["days"] else "")
                for r in rows]
        return csv_response(f"attendance-{month}.csv",
                            ["admission_no", "name", "days_marked", "attended", "absent", "percent"], data)
    return render_template("attendance_report.html", batches=batches, batch_id=batch_id,
                           month=month, rows=rows, day=day, daily=daily)
