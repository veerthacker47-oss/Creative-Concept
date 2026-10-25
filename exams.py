import math

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import audit, execute, get_setting, query
from ..security import has_perm, permission_required
from ..utils import csv_response, grade_for, parse_date, today_local

bp = Blueprint("exams", __name__, url_prefix="/exams")


def _batches():
    return query("SELECT id, name FROM batches WHERE active=1 ORDER BY name")


def _pass_pct():
    try:
        return float(get_setting("pass_percentage", "35"))
    except ValueError:
        return 35.0


def _pass_threshold(exam):
    """Marks needed to pass this exam: the exam's own pass mark, else the institute pass percentage."""
    if exam["pass_marks"] is not None:
        return float(exam["pass_marks"])
    return exam["max_marks"] * _pass_pct() / 100


def _parse_number(raw):
    """Return a finite float or None. Rejects text, NaN and infinity."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


@bp.route("/")
@permission_required("academics.view")
def index():
    exams = query(
        "SELECT e.*, b.name AS batch_name,"
        " (SELECT COUNT(*) FROM marks m WHERE m.exam_id=e.id) AS entered"
        " FROM exams e JOIN batches b ON b.id=e.batch_id ORDER BY e.exam_date DESC, e.id DESC")
    return render_template("exams.html", exams=exams, batches=_batches(), today=today_local())


@bp.route("/new", methods=["POST"])
@permission_required("academics.edit")
def create():
    name = (request.form.get("name") or "").strip()[:120]
    subject = (request.form.get("subject") or "").strip()[:80] or None
    batch_id = request.form.get("batch_id", type=int)
    exam_date = parse_date(request.form.get("exam_date"))
    max_marks = _parse_number(request.form.get("max_marks"))
    pass_raw = (request.form.get("pass_marks") or "").strip()
    pass_marks = _parse_number(pass_raw) if pass_raw else None
    if not name or not batch_id or max_marks is None or max_marks <= 0:
        flash("Exam needs a name, batch and maximum marks above zero.", "error")
        return redirect(url_for("exams.index"))
    if pass_raw and (pass_marks is None or pass_marks < 0 or pass_marks > max_marks):
        flash("Passing marks must be a number between 0 and the maximum marks.", "error")
        return redirect(url_for("exams.index"))
    if not query("SELECT 1 FROM batches WHERE id=?", (batch_id,), one=True):
        flash("Choose a valid batch.", "error")
        return redirect(url_for("exams.index"))
    if query("SELECT 1 FROM exams WHERE name=? AND batch_id=?", (name, batch_id), one=True):
        flash("This exam already exists for that batch.", "error")
        return redirect(url_for("exams.index"))
    eid = execute(
        "INSERT INTO exams(name, batch_id, exam_date, max_marks, subject, pass_marks) VALUES (?,?,?,?,?,?)",
        (name, batch_id, exam_date, max_marks, subject, pass_marks)).lastrowid
    audit("exam.created", "exam", eid, name)
    flash("Exam created. Now enter marks.", "ok")
    return redirect(url_for("exams.detail", eid=eid))


@bp.route("/<int:eid>", methods=["GET", "POST"])
@permission_required("academics.view")
def detail(eid):
    exam = query("SELECT e.*, b.name AS batch_name FROM exams e JOIN batches b ON b.id=e.batch_id"
                 " WHERE e.id=?", (eid,), one=True)
    if not exam:
        return render_template("error.html", code=404, message="Exam not found."), 404
    students = query("SELECT id, admission_no, first_name, last_name FROM students"
                     " WHERE batch_id=? AND status='active' ORDER BY first_name", (exam["batch_id"],))
    can_edit = has_perm("academics.edit")
    if request.method == "POST":
        if not can_edit:
            return render_template("error.html", code=403,
                                   message="You do not have permission to enter marks."), 403
        saved, problems = 0, []
        single_student = request.form.get("save_student", type=int)
        clear_student = request.form.get("clear_student", type=int)
        if clear_student:
            single_student = clear_student
        if single_student and not any(s["id"] == single_student for s in students):
            flash("That student is not active in this exam's batch.", "error")
            return redirect(url_for("exams.detail", eid=eid))
        for s in students:
            if single_student and s["id"] != single_student:
                continue
            raw = (request.form.get(f"m_{s['id']}") or "").strip()
            remarks = (request.form.get(f"r_{s['id']}") or "").strip()[:200]
            if clear_student == s["id"]:
                execute("DELETE FROM marks WHERE exam_id=? AND student_id=?", (eid, s["id"]))
                saved += 1
                continue
            if raw == "":
                continue                       # blank = not entered; existing marks are left alone
            if raw.upper() == "AB":
                absent, value = 1, None
            else:
                value = _parse_number(raw)
                if value is None:
                    problems.append(f"{s['first_name']}: '{raw}' is not a valid number.")
                    continue
                if value < 0 or value > exam["max_marks"]:
                    problems.append(f"{s['first_name']}: marks must be between 0 and {exam['max_marks']:g}.")
                    continue
                absent = 0
            execute(
                "INSERT INTO marks(exam_id, student_id, marks, absent, remarks, updated_by, updated_at)"
                " VALUES (?,?,?,?,?,?,datetime('now'))"
                " ON CONFLICT(exam_id, student_id) DO UPDATE SET marks=excluded.marks,"
                " absent=excluded.absent, remarks=excluded.remarks, updated_by=excluded.updated_by,"
                " updated_at=excluded.updated_at",
                (eid, s["id"], value, absent, remarks, session.get("user_id")),
            )
            saved += 1
        for p in problems:
            flash(p, "error")
        audit("marks.saved", "exam", eid, f"{saved} rows")
        if saved:
            flash(("Student mark updated." if single_student else f"Marks saved for {saved} student(s)."), "ok")
        elif not problems:
            flash("No marks changed. Enter a mark, type AB, or use Clear to remove an existing entry.", "error")
        return redirect(url_for("exams.detail", eid=eid))

    marks = {r["student_id"]: r for r in query("SELECT * FROM marks WHERE exam_id=?", (eid,))}
    analytics = _analytics(exam, marks)
    threshold = _pass_threshold(exam)
    return render_template("exam_detail.html", exam=exam, students=students, marks=marks,
                           analytics=analytics, can_edit=can_edit, pass_pct=_pass_pct(),
                           threshold=threshold)


def _analytics(exam, marks):
    scores = [m["marks"] for m in marks.values() if not m["absent"] and m["marks"] is not None]
    max_marks = exam["max_marks"]
    if not scores:
        return None
    threshold = _pass_threshold(exam)
    pct = [100 * s / max_marks for s in scores]
    passed = sum(1 for s in scores if s >= threshold)
    distribution = {}
    for p in pct:
        distribution[grade_for(p)] = distribution.get(grade_for(p), 0) + 1
    ordered = sorted(
        ((m["student_id"], m["marks"]) for m in marks.values() if not m["absent"] and m["marks"] is not None),
        key=lambda t: -t[1])
    names = {r["id"]: f"{r['first_name']} {r['last_name'] or ''}".strip()
             for r in query("SELECT id, first_name, last_name FROM students WHERE batch_id=?",
                            (exam["batch_id"],))}
    return {
        "count": len(scores),
        "absent": sum(1 for m in marks.values() if m["absent"]),
        "average": round(sum(scores) / len(scores), 2),
        "average_pct": round(sum(pct) / len(pct), 1),
        "highest": max(scores),
        "lowest": min(scores),
        "pass_rate": round(100 * passed / len(scores), 1),
        "distribution": sorted(distribution.items()),
        "top": [(names.get(sid, "?"), mk) for sid, mk in ordered[:5]],
    }


@bp.route("/analytics")
@permission_required("reports.view")
def performance_analytics():
    """Batch-wide performance overview with subject averages and recent score changes."""
    batch_id = request.args.get("batch_id", type=int)
    batches = _batches()
    students = []
    subject_rows = []
    if batch_id:
        roster = query(
            "SELECT id, admission_no, first_name, last_name FROM students"
            " WHERE batch_id=? AND status='active' ORDER BY first_name, last_name", (batch_id,))
        all_marks = query(
            "SELECT m.student_id, m.marks, m.absent, e.name, e.subject, e.max_marks, e.exam_date, e.id AS exam_id"
            " FROM marks m JOIN exams e ON e.id=m.exam_id WHERE e.batch_id=?"
            " ORDER BY COALESCE(e.exam_date, ''), e.id", (batch_id,))
        by_student, by_subject = {}, {}
        for row in all_marks:
            item = dict(row)
            if item["absent"] or item["marks"] is None:
                continue
            pct = 100 * item["marks"] / item["max_marks"]
            by_student.setdefault(item["student_id"], []).append({**item, "pct": pct})
            subject = item["subject"] or "General"
            bucket = by_subject.setdefault(subject, {"total_pct": 0.0, "count": 0})
            bucket["total_pct"] += pct
            bucket["count"] += 1
        for student in roster:
            records = by_student.get(student["id"], [])
            avg = round(sum(r["pct"] for r in records) / len(records), 1) if records else None
            latest = records[-1] if records else None
            previous = records[-2] if len(records) > 1 else None
            change = round(latest["pct"] - previous["pct"], 1) if latest and previous else None
            students.append({"id": student["id"], "admission_no": student["admission_no"],
                             "name": f"{student['first_name']} {student['last_name'] or ''}".strip(),
                             "average": avg, "exams": len(records),
                             "latest": latest["pct"] if latest else None,
                             "change": change,
                             "review": bool(change is not None and change <= -10)})
        subject_rows = [{"subject": name, "average": round(v["total_pct"] / v["count"], 1), "count": v["count"]}
                        for name, v in sorted(by_subject.items())]
        students.sort(key=lambda s: (s["average"] is None, -(s["average"] or 0), s["name"]))
    return render_template("performance_analytics.html", batches=batches, batch_id=batch_id,
                           students=students, subject_rows=subject_rows)


@bp.route("/report-cards")
@permission_required("reports.view")
def report_cards():
    """Pick a student and open their printable report card. Lists active students of one batch."""
    batch_id = request.args.get("batch_id", type=int)
    students = []
    if batch_id:
        students = query(
            "SELECT s.id, s.admission_no, s.first_name, s.last_name, COUNT(m.id) AS exams_with_marks"
            " FROM students s LEFT JOIN marks m ON m.student_id=s.id"
            " WHERE s.batch_id=? AND s.status='active' GROUP BY s.id ORDER BY s.first_name",
            (batch_id,))
    return render_template("report_cards.html", batches=_batches(), batch_id=batch_id, students=students)


@bp.route("/report/<int:sid>")
@permission_required("reports.view")
def report_card(sid):
    """Printable report card: every exam with marks, subject, pass/fail, rank and subject totals."""
    student = query("SELECT s.*, b.name AS batch_name FROM students s"
                    " LEFT JOIN batches b ON b.id=s.batch_id WHERE s.id=?", (sid,), one=True)
    if not student:
        return render_template("error.html", code=404, message="Student not found."), 404
    rows = query(
        "SELECT e.id AS exam_id, e.name, e.subject, e.exam_date, e.max_marks, e.pass_marks,"
        " m.marks, m.absent, m.remarks"
        " FROM marks m JOIN exams e ON e.id=m.exam_id WHERE m.student_id=? ORDER BY e.exam_date, e.id",
        (sid,))
    report, total, total_max, subjects = [], 0.0, 0.0, {}
    for r in rows:
        item = dict(r)
        item["threshold"] = _pass_threshold(r)
        if r["absent"] or r["marks"] is None:
            item.update(percent=None, grade="AB", rank=None, outof=None, status="AB")
        else:
            pct = 100 * r["marks"] / r["max_marks"]
            higher = query("SELECT COUNT(*) AS n FROM marks WHERE exam_id=? AND absent=0"
                           " AND marks > ?", (r["exam_id"], r["marks"]), one=True)["n"]
            outof = query("SELECT COUNT(*) AS n FROM marks WHERE exam_id=? AND absent=0",
                          (r["exam_id"],), one=True)["n"]
            item.update(percent=round(pct, 1), grade=grade_for(pct), rank=higher + 1, outof=outof,
                        status="Pass" if r["marks"] >= item["threshold"] else "Fail")
            total += r["marks"]
            total_max += r["max_marks"]
            key = r["subject"] or "General"
            bucket = subjects.setdefault(key, {"marks": 0.0, "max": 0.0, "exams": 0})
            bucket["marks"] += r["marks"]
            bucket["max"] += r["max_marks"]
            bucket["exams"] += 1
        report.append(item)
    subject_rows = [
        {"subject": k, "marks": round(v["marks"], 2), "max": round(v["max"], 2), "exams": v["exams"],
         "percent": round(100 * v["marks"] / v["max"], 1) if v["max"] else None}
        for k, v in sorted(subjects.items())
    ]
    overall = round(100 * total / total_max, 1) if total_max else None
    return render_template("report_card.html", student=student, report=report, overall=overall,
                           overall_grade=grade_for(overall), pass_pct=_pass_pct(),
                           subject_rows=subject_rows)


@bp.route("/export/<int:eid>.csv")
@permission_required("reports.view")
def export_marks(eid):
    exam = query("SELECT * FROM exams WHERE id=?", (eid,), one=True)
    if not exam:
        return render_template("error.html", code=404, message="Exam not found."), 404
    rows = query(
        "SELECT s.admission_no, s.first_name, s.last_name, m.marks, m.absent, m.remarks"
        " FROM students s LEFT JOIN marks m ON m.student_id=s.id AND m.exam_id=?"
        " WHERE s.batch_id=? AND s.status='active' ORDER BY s.first_name", (eid, exam["batch_id"]))
    threshold = _pass_threshold(exam)
    data = []
    for r in rows:
        if r["absent"]:
            result = "AB"
        elif r["marks"] is None:
            result = ""
        else:
            result = "Pass" if r["marks"] >= threshold else "Fail"
        data.append((r["admission_no"], f"{r['first_name']} {r['last_name'] or ''}".strip(),
                     "AB" if r["absent"] else (r["marks"] if r["marks"] is not None else ""),
                     exam["max_marks"], result, r["remarks"] or ""))
    return csv_response(f"marks-{eid}.csv",
                        ["admission_no", "name", "marks", "max", "result", "remarks"], data)
