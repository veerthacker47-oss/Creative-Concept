from flask import Blueprint, render_template, request

from ..db import audit, query
from ..security import permission_required
from ..utils import csv_response, parse_date, today_local

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@permission_required("reports.view")
def index():
    batches = query("SELECT id, name FROM batches ORDER BY name")
    exams = query("SELECT e.id, e.name, b.name AS batch_name FROM exams e"
                  " JOIN batches b ON b.id=e.batch_id ORDER BY e.exam_date DESC LIMIT 100")
    return render_template("reports.html", batches=batches, exams=exams, today=today_local())


@bp.route("/payments.csv")
@permission_required("reports.view")
def payments_csv():
    start = parse_date(request.args.get("start")) or today_local()[:8] + "01"
    end = parse_date(request.args.get("end")) or today_local()
    rows = query(
        "SELECT p.paid_on, p.receipt_no, s.admission_no, s.first_name, s.last_name, p.amount_paise,"
        " p.method, p.reference, u.full_name FROM payments p JOIN students s ON s.id=p.student_id"
        " LEFT JOIN users u ON u.id=p.recorded_by WHERE p.paid_on BETWEEN ? AND ?"
        " ORDER BY p.paid_on, p.id", (start, end))
    audit("export.payments", "payments", None, f"{start}..{end} {len(rows)} rows")
    data = [(r["paid_on"], r["receipt_no"], r["admission_no"],
             f"{r['first_name']} {r['last_name'] or ''}".strip(), round(r["amount_paise"] / 100, 2),
             r["method"], r["reference"] or "", r["full_name"] or "") for r in rows]
    total = sum(r["amount_paise"] for r in rows)
    data.append(("TOTAL", "", "", "", round(total / 100, 2), "", "", ""))
    return csv_response(f"payments-{start}-to-{end}.csv",
                        ["date", "receipt", "admission_no", "name", "amount_rupees", "method",
                         "reference", "recorded_by"], data)


@bp.route("/attendance.csv")
@permission_required("reports.view")
def attendance_csv():
    start = parse_date(request.args.get("start")) or today_local()[:8] + "01"
    end = parse_date(request.args.get("end")) or today_local()
    rows = query(
        "SELECT a.att_date, s.admission_no, s.first_name, s.last_name, b.name, a.status"
        " FROM attendance a JOIN students s ON s.id=a.student_id"
        " LEFT JOIN batches b ON b.id=a.batch_id WHERE a.att_date BETWEEN ? AND ?"
        " ORDER BY a.att_date, b.name, s.first_name", (start, end))
    audit("export.attendance", "attendance", None, f"{start}..{end} {len(rows)} rows")
    data = [(r["att_date"], r["admission_no"], f"{r['first_name']} {r['last_name'] or ''}".strip(),
             r["name"] or "", r["status"]) for r in rows]
    return csv_response(f"attendance-{start}-to-{end}.csv",
                        ["date", "admission_no", "name", "batch", "status"], data)


@bp.route("/marks.csv")
@permission_required("reports.view")
def marks_csv():
    rows = query(
        "SELECT e.name AS exam, e.exam_date, b.name AS batch, s.admission_no,"
        " s.first_name, s.last_name, m.marks, m.absent, e.max_marks FROM marks m"
        " JOIN exams e ON e.id=m.exam_id JOIN batches b ON b.id=e.batch_id"
        " JOIN students s ON s.id=m.student_id ORDER BY e.exam_date, e.name, s.first_name")
    audit("export.marks", "marks", None, f"{len(rows)} rows")
    data = [(r["exam"], r["exam_date"] or "", r["batch"], r["admission_no"],
             f"{r['first_name']} {r['last_name'] or ''}".strip(),
             "AB" if r["absent"] else (r["marks"] if r["marks"] is not None else ""),
             r["max_marks"]) for r in rows]
    return csv_response("marks-all.csv",
                        ["exam", "date", "batch", "admission_no", "name", "marks", "max"], data)
