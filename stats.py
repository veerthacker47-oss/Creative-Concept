"""Live numbers for the dashboard. Computed from the database on every call (no cached fake data)."""
from ..db import query
from ..utils import now_local, today_local
from .fees import outstanding_report


def collect_stats():
    today = today_local()
    month_start = today[:8] + "01"

    active_students = query(
        "SELECT COUNT(*) AS n FROM students WHERE status='active'", one=True
    )["n"]
    batches = query("SELECT COUNT(*) AS n FROM batches WHERE active=1", one=True)["n"]

    att = query(
        "SELECT SUM(status='present') AS present, SUM(status='absent') AS absent,"
        " SUM(status='late') AS late, COUNT(*) AS total FROM attendance WHERE att_date=?",
        (today,), one=True,
    )
    collected = query(
        "SELECT COALESCE(SUM(amount_paise),0) AS n FROM payments WHERE paid_on>=? AND paid_on<=?",
        (month_start, today), one=True,
    )["n"]

    outstanding = outstanding_report()
    total_outstanding = sum(r["outstanding"] for r in outstanding)
    overdue_students = sum(1 for r in outstanding if r["has_overdue"])

    notif = query(
        "SELECT SUM(status='queued') AS queued, SUM(status='failed') AS failed,"
        " SUM(status='sent' AND sent_at>=datetime('now','-1 day')) AS sent_24h FROM notifications",
        one=True,
    )
    upcoming_exams = query(
        "SELECT COUNT(*) AS n FROM exams WHERE exam_date>=?", (today,), one=True
    )["n"]
    announcements = query(
        "SELECT id, title, created_at FROM announcements ORDER BY id DESC LIMIT 5"
    )

    return {
        "today": today,
        "updated_at": now_local().strftime("%d %b %Y, %H:%M:%S"),
        "active_students": active_students,
        "batches": batches,
        "attendance_marked_today": att["total"] or 0,
        "present_today": att["present"] or 0,
        "absent_today": att["absent"] or 0,
        "late_today": att["late"] or 0,
        "attendance_pct_today": (
            round(100 * ((att["present"] or 0) + (att["late"] or 0)) / att["total"], 1)
            if att["total"] else None),
        "collected_this_month_paise": collected,
        "outstanding_paise": total_outstanding,
        "overdue_students": overdue_students,
        "queued_notifications": notif["queued"] or 0,
        "failed_notifications": notif["failed"] or 0,
        "sent_last_24h": notif["sent_24h"] or 0,
        "upcoming_exams": upcoming_exams,
        "recent_announcements": [dict(a) for a in announcements],
    }
