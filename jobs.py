"""Scheduled workflows. Every job is idempotent: running it twice never duplicates messages or invoices."""
import logging

from .db import create_backup, execute, get_setting, query
from .services import notify
from .services.fees import outstanding_report
from .utils import month_of, now_local, today_local

log = logging.getLogger("institute.jobs")


def job_send_queued():
    return notify.send_queued()


def job_fee_reminders():
    """Once per student, per channel, per month, for students with overdue balances."""
    month = month_of(today_local())
    created = 0
    for row in outstanding_report():
        if row["overdue_amount"] <= 0:
            continue
        student = query("SELECT * FROM students WHERE id=?", (row["id"],), one=True)
        for channel, recipient in notify.parent_channels(student):
            body = (
                f"Dear {student['parent_name']}, the fee balance for {student['first_name']}"
                f" ({student['admission_no']}) is {_money(row['outstanding'])}, of which"
                f" {_money(row['overdue_amount'])} is overdue. Please clear it at the earliest."
                f" - {get_setting('institute_name', 'The Institute')}"
            )
            if notify.enqueue(student["id"], channel, recipient, "fee_reminder", body,
                              f"fee-reminder:{student['id']}:{month}:{channel}",
                              subject="Fee payment reminder"):
                created += 1
    counts = notify.send_queued()
    return {"created": created, **counts}


def job_monthly_invoices():
    """Create this month's tuition invoices. UNIQUE(student_id, period) prevents double billing."""
    today = today_local()
    period = month_of(today)
    due_day = int(get_setting("fee_due_day", "10") or 10)
    due_date = f"{period}-{due_day:02d}"
    cur = execute(
        "INSERT OR IGNORE INTO invoices(student_id, description, period, amount_paise, due_date)"
        " SELECT s.id, 'Tuition fee ' || ?, ?, b.monthly_fee_paise, ?"
        " FROM students s JOIN batches b ON b.id = s.batch_id"
        " WHERE s.status='active' AND b.monthly_fee_paise > 0",
        (period, period, due_date),
    )
    return cur.rowcount


def job_backup():
    path = create_backup(
        _db_path(), _backup_dir(), _backup_keep()
    )
    log.info("Backup written to %s", path)
    return path


def run_all(app):
    """Run every daily job once. Used by cron: `flask run-jobs`."""
    with app.app_context():
        results = {
            "monthly_invoices": job_monthly_invoices(),
            "fee_reminders": job_fee_reminders(),
            "queued_messages": job_send_queued(),
            "backup": job_backup(),
        }
    return results


def start_scheduler(app):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        log.warning("APScheduler not installed; scheduled jobs are off. Use `flask run-jobs` from cron.")
        return None
    tz = app.config["TIMEZONE"]
    sched = BackgroundScheduler(timezone=tz)

    def wrap(fn):
        def run():
            with app.app_context():
                try:
                    fn()
                except Exception:
                    log.exception("Scheduled job %s failed", fn.__name__)
        run.__name__ = fn.__name__
        return run

    sched.add_job(wrap(job_send_queued), "interval", minutes=5, id="send_queued",
                  max_instances=1, coalesce=True)
    sched.add_job(wrap(job_monthly_invoices), "cron", hour=6, minute=30, id="monthly_invoices")
    sched.add_job(wrap(job_fee_reminders), "cron", hour=9, minute=0, id="fee_reminders")
    sched.add_job(wrap(job_backup), "cron", hour=2, minute=0, id="backup")
    sched.start()
    app.extensions["scheduler"] = sched
    log.info("Scheduler started at %s", now_local().isoformat())
    return sched


def _money(paise):
    from .utils import fmt_money
    return fmt_money(paise)


def _db_path():
    from flask import current_app
    return current_app.config["DATABASE"]


def _backup_dir():
    from flask import current_app
    return current_app.config["BACKUP_DIR"]


def _backup_keep():
    from flask import current_app
    return current_app.config["BACKUP_KEEP"]
