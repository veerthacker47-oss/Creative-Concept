import csv
import io
from datetime import date

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import audit, execute, query
from ..security import permission_required
from ..services.fees import student_ledger
from ..utils import csv_response, normalize_phone, parse_date, today_local, valid_email

bp = Blueprint("students", __name__, url_prefix="/students")

PER_PAGE = 50
STATUSES = ("active", "inactive", "left")
GENDERS = ("", "Female", "Male", "Other")


def clean_student(data):
    """Validate and normalise student fields. Returns (cleaned_dict, list_of_errors)."""
    errors = []
    out = {
        "first_name": (data.get("first_name") or "").strip(),
        "last_name": (data.get("last_name") or "").strip(),
        "gender": (data.get("gender") or "").strip(),
        "dob": parse_date(data.get("dob")),
        "phone": normalize_phone(data.get("phone") or ""),
        "email": (data.get("email") or "").strip(),
        "address": (data.get("address") or "").strip(),
        "parent_name": (data.get("parent_name") or "").strip(),
        "parent_phone": normalize_phone(data.get("parent_phone") or ""),
        "parent_email": (data.get("parent_email") or "").strip(),
        "joined_on": parse_date(data.get("joined_on")) or today_local(),
        "batch_id": data.get("batch_id") or None,
        "status": (data.get("status") or "active").strip(),
        "privacy_notice_acknowledged": data.get("privacy_notice_acknowledged") == "1",
    }
    if not out["first_name"]:
        errors.append("First name is required.")
    if not out["parent_name"]:
        errors.append("Parent / guardian name is required.")
    if not out["parent_phone"] and not out["parent_email"]:
        errors.append("Provide at least a parent phone number or email for notifications.")
    if out["parent_email"] and not valid_email(out["parent_email"]):
        errors.append("Parent email looks invalid.")
    if out["email"] and not valid_email(out["email"]):
        errors.append("Student email looks invalid.")
    if data.get("dob") and not out["dob"]:
        errors.append("Date of birth must be YYYY-MM-DD.")
    if out["status"] not in STATUSES:
        errors.append("Invalid status.")
    if out["gender"] not in GENDERS:
        errors.append("Invalid gender value.")
    if not out["privacy_notice_acknowledged"]:
        errors.append("Confirm that the privacy notice and any required guardian consent/lawful basis have been handled before saving this record.")
    return out, errors


def _batches():
    return query("SELECT id, name FROM batches WHERE active=1 ORDER BY name")


def next_admission_no():
    year = date.today().year
    n = query("SELECT COUNT(*) AS n FROM students", one=True)["n"] + 1
    while True:
        candidate = f"ADM{year}-{n:04d}"
        if not query("SELECT 1 FROM students WHERE admission_no=?", (candidate,), one=True):
            return candidate
        n += 1


@bp.route("/")
@permission_required("students.view")
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    batch_id = request.args.get("batch_id", "")
    page = max(int(request.args.get("page", 1) or 1), 1)
    where, args = [], []
    if q:
        where.append("(s.first_name LIKE ? OR s.last_name LIKE ? OR s.admission_no LIKE ?"
                     " OR s.parent_name LIKE ? OR s.parent_phone LIKE ?)")
        args += [f"%{q}%"] * 5
    if status in STATUSES:
        where.append("s.status=?")
        args.append(status)
    if batch_id:
        where.append("s.batch_id=?")
        args.append(batch_id)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = query(f"SELECT COUNT(*) AS n FROM students s {clause}", args, one=True)["n"]
    rows = query(
        f"SELECT s.*, b.name AS batch_name FROM students s LEFT JOIN batches b ON b.id=s.batch_id"
        f" {clause} ORDER BY s.first_name, s.last_name LIMIT ? OFFSET ?",
        args + [PER_PAGE, (page - 1) * PER_PAGE],
    )
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    return render_template("students_list.html", students=rows, total=total, page=page,
                           pages=pages, q=q, status=status, batch_id=batch_id,
                           batches=_batches(), statuses=STATUSES)


@bp.route("/new", methods=["GET", "POST"])
@permission_required("students.edit")
def new():
    if request.method == "POST":
        data, errors = clean_student(request.form)
        admission = (request.form.get("admission_no") or "").strip() or next_admission_no()
        if query("SELECT 1 FROM students WHERE admission_no=?", (admission,), one=True):
            errors.append(f"Admission number {admission} already exists.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("student_form.html", student=data, batches=_batches(),
                                   statuses=STATUSES, genders=GENDERS, mode="new",
                                   admission_no=admission), 400
        sid = execute(
            "INSERT INTO students(admission_no, first_name, last_name, gender, dob, phone, email,"
            " address, parent_name, parent_phone, parent_email, batch_id, status, joined_on,"
            " privacy_notice_acknowledged, privacy_notice_acknowledged_at, privacy_notice_version, privacy_notice_acknowledged_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),'v1',?)",
            (admission, data["first_name"], data["last_name"], data["gender"], data["dob"],
             data["phone"], data["email"], data["address"], data["parent_name"],
             data["parent_phone"], data["parent_email"], data["batch_id"], data["status"],
             data["joined_on"], 1, g.user["id"]),
        ).lastrowid
        audit("student.created", "student", sid, admission)
        flash(f"Student {data['first_name']} added as {admission}.", "ok")
        return redirect(url_for("students.detail", sid=sid))
    return render_template("student_form.html", student={"status": "active", "joined_on": today_local()},
                           batches=_batches(), statuses=STATUSES, genders=GENDERS,
                           mode="new", admission_no=next_admission_no())


@bp.route("/<int:sid>")
@permission_required("students.view")
def detail(sid):
    student = query(
        "SELECT s.*, b.name AS batch_name FROM students s LEFT JOIN batches b ON b.id=s.batch_id"
        " WHERE s.id=?", (sid,), one=True)
    if not student:
        return render_template("error.html", code=404, message="Student not found."), 404
    att = query(
        "SELECT SUM(status IN ('present','late')) AS attended, COUNT(*) AS total,"
        " SUM(status='absent') AS absent FROM attendance WHERE student_id=?", (sid,), one=True)
    recent_att = query(
        "SELECT att_date, status FROM attendance WHERE student_id=? ORDER BY att_date DESC LIMIT 15",
        (sid,))
    marks = query(
        "SELECT e.name, e.exam_date, e.max_marks, m.marks, m.absent FROM marks m"
        " JOIN exams e ON e.id=m.exam_id WHERE m.student_id=? ORDER BY e.exam_date DESC LIMIT 10",
        (sid,))
    notes = query(
        "SELECT channel, kind, status, body, created_at FROM notifications WHERE student_id=?"
        " ORDER BY id DESC LIMIT 10", (sid,))
    return render_template(
        "student_detail.html", student=student, att=att, recent_att=recent_att,
        marks=marks, notes=notes, ledger=student_ledger(sid),
    )


@bp.route("/<int:sid>/edit", methods=["GET", "POST"])
@permission_required("students.edit")
def edit(sid):
    current = query("SELECT * FROM students WHERE id=?", (sid,), one=True)
    if not current:
        return render_template("error.html", code=404, message="Student not found."), 404
    if request.method == "POST":
        data, errors = clean_student(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            data["id"] = sid
            return render_template("student_form.html", student=data, batches=_batches(),
                                   statuses=STATUSES, genders=GENDERS, mode="edit",
                                   admission_no=current["admission_no"]), 400
        execute(
            "UPDATE students SET first_name=?, last_name=?, gender=?, dob=?, phone=?, email=?,"
            " address=?, parent_name=?, parent_phone=?, parent_email=?, batch_id=?, status=?,"
            " joined_on=?, privacy_notice_acknowledged=1, privacy_notice_acknowledged_at=datetime('now'),"
            " privacy_notice_version='v1', privacy_notice_acknowledged_by=?, updated_at=datetime('now') WHERE id=?",
            (data["first_name"], data["last_name"], data["gender"], data["dob"], data["phone"],
             data["email"], data["address"], data["parent_name"], data["parent_phone"],
             data["parent_email"], data["batch_id"], data["status"], data["joined_on"], g.user["id"], sid),
        )
        audit("student.updated", "student", sid)
        flash("Student details saved.", "ok")
        return redirect(url_for("students.detail", sid=sid))
    return render_template("student_form.html", student=dict(current), batches=_batches(),
                           statuses=STATUSES, genders=GENDERS, mode="edit",
                           admission_no=current["admission_no"])


@bp.route("/<int:sid>/status", methods=["POST"])
@permission_required("students.edit")
def set_status(sid):
    """Students are never deleted (financial and attendance history must stay); they are deactivated."""
    status = request.form.get("status", "")
    if status not in STATUSES:
        flash("Invalid status.", "error")
    else:
        execute("UPDATE students SET status=?, updated_at=datetime('now') WHERE id=?", (status, sid))
        audit("student.status", "student", sid, status)
        flash(f"Status set to {status}.", "ok")
    return redirect(url_for("students.detail", sid=sid))


@bp.route("/import", methods=["GET", "POST"])
@permission_required("import.run")
def import_csv():
    """Import students from CSV. Bad rows are reported and skipped; good rows are saved."""
    result = None
    if request.method == "POST":
        upload = request.files.get("file")
        preview = request.form.get("preview") == "1"
        privacy_ack = request.form.get("privacy_notice_acknowledged") == "1"
        if not preview and not privacy_ack:
            flash("Confirm that the privacy notice and any required consent/lawful basis have been handled before importing student records.", "error")
            return redirect(url_for("students.import_csv"))
        if not upload or not upload.filename.lower().endswith(".csv"):
            flash("Choose a .csv file exported from a spreadsheet.", "error")
            return redirect(url_for("students.import_csv"))
        text = upload.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        batch_map = {r["name"].lower(): r["id"] for r in _batches()}
        created, skipped = [], []
        for line_no, row in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            if not any(row.values()):
                continue
            # Preview validates records without persisting the staff acknowledgement.
            row["privacy_notice_acknowledged"] = "1" if (preview or privacy_ack) else "0"
            data, errors = clean_student(row)
            batch_name = row.get("batch_name", "").lower()
            if batch_name:
                if batch_name in batch_map:
                    data["batch_id"] = batch_map[batch_name]
                else:
                    errors.append(f"Batch '{row.get('batch_name')}' does not exist.")
            admission = row.get("admission_no") or ""
            if admission and query("SELECT 1 FROM students WHERE admission_no=?", (admission,), one=True):
                errors.append(f"Admission number {admission} already exists.")
            if errors:
                skipped.append((line_no, "; ".join(errors)))
                continue
            admission = admission or next_admission_no()
            created.append((line_no, admission, data["first_name"]))
            if not preview:
                sid = execute(
                    "INSERT INTO students(admission_no, first_name, last_name, gender, dob, phone,"
                    " email, address, parent_name, parent_phone, parent_email, batch_id, status,"
                    " joined_on, privacy_notice_acknowledged, privacy_notice_acknowledged_at,"
                    " privacy_notice_version, privacy_notice_acknowledged_by)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),'v1',?)",
                    (admission, data["first_name"], data["last_name"], data["gender"], data["dob"],
                     data["phone"], data["email"], data["address"], data["parent_name"],
                     data["parent_phone"], data["parent_email"], data["batch_id"], data["status"],
                     data["joined_on"], 1, g.user["id"]),
                ).lastrowid
                audit("student.imported", "student", sid, admission)
        result = {"created": created, "skipped": skipped, "preview": preview}
    return render_template("students_import.html", result=result)


@bp.route("/export.csv")
@permission_required("reports.view")
def export_csv():
    rows = query(
        "SELECT s.admission_no, s.first_name, s.last_name, s.gender, s.dob, s.phone, s.email,"
        " s.parent_name, s.parent_phone, s.parent_email, b.name, s.status, s.joined_on"
        " FROM students s LEFT JOIN batches b ON b.id=s.batch_id ORDER BY s.admission_no")
    audit("export.students", "student", None, f"{len(rows)} rows")
    headers = ["admission_no", "first_name", "last_name", "gender", "dob", "phone", "email",
               "parent_name", "parent_phone", "parent_email", "batch_name", "status", "joined_on"]
    return csv_response("students.csv", headers, [tuple(r) for r in rows])
