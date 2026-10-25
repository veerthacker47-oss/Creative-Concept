from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..db import audit, execute, query
from ..security import permission_required
from ..services import notify

bp = Blueprint("comms", __name__, url_prefix="/comms")

HISTORY_LIMIT = 200


@bp.route("/")
@permission_required("comms.send")
def index():
    status = request.args.get("status", "")
    channel = request.args.get("channel", "")
    where, args = [], []
    if status in ("queued", "sent", "failed"):
        where.append("n.status=?")
        args.append(status)
    if channel in notify.CHANNELS:
        where.append("n.channel=?")
        args.append(channel)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    history = query(
        f"SELECT n.*, s.first_name, s.last_name, s.admission_no FROM notifications n"
        f" LEFT JOIN students s ON s.id=n.student_id {clause}"
        f" ORDER BY n.id DESC LIMIT {HISTORY_LIMIT}", args)
    counts = query("SELECT status, COUNT(*) AS n FROM notifications GROUP BY status")
    totals = {r["status"]: r["n"] for r in counts}
    return render_template("comms.html", history=history, totals=totals, status=status,
                           channel=channel, channels=notify.CHANNELS,
                           announcements=query("SELECT a.*, b.name AS batch_name FROM announcements a"
                                               " LEFT JOIN batches b ON b.id=a.batch_id"
                                               " ORDER BY a.id DESC LIMIT 20"))


@bp.route("/retry", methods=["POST"])
@permission_required("comms.send")
def retry():
    reset = notify.retry_failed()
    counts = notify.send_queued()
    audit("comms.retry", "notifications", None, str(counts))
    flash(f"Re-queued {reset} failed message(s). Sent: {counts['sent']}, still waiting: "
          f"{counts['waiting']}, failed: {counts['failed']}.", "ok")
    return redirect(url_for("comms.index"))


@bp.route("/broadcast", methods=["GET", "POST"])
@permission_required("comms.send")
def broadcast():
    batches = query("SELECT id, name FROM batches WHERE active=1 ORDER BY name")
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        body = (request.form.get("body") or "").strip()
        audience = request.form.get("audience", "all")
        batch_id = request.form.get("batch_id", type=int) if audience != "all" else None
        channels = [c for c in request.form.getlist("channels") if c in notify.CHANNELS]
        if not title or not body:
            flash("Title and message are required.", "error")
            return redirect(url_for("comms.broadcast"))
        if not channels:
            flash("Choose at least one channel (email, SMS or WhatsApp) to send this to parents.", "error")
            return redirect(url_for("comms.broadcast"))
        if audience != "all" and not batch_id:
            flash("Choose a batch for the audience.", "error")
            return redirect(url_for("comms.broadcast"))
        # Duplicate prevention: the same announcement cannot be created twice within 10 minutes.
        if query("SELECT 1 FROM announcements WHERE title=? AND body=?"
                 " AND created_at >= datetime('now','-10 minutes')", (title, body), one=True):
            flash("This exact announcement was just posted. Not sending it twice.", "error")
            return redirect(url_for("comms.index"))
        aid = execute(
            "INSERT INTO announcements(title, body, batch_id, channels, created_by)"
            " VALUES (?,?,?,?,?)",
            (title, body, batch_id, ",".join(channels), session.get("user_id")),
        ).lastrowid
        sql = "SELECT * FROM students WHERE status='active'"
        args = ()
        if batch_id:
            sql += " AND batch_id=?"
            args = (batch_id,)
        queued = 0
        recipients = set()
        for student in query(sql, args):
            for channel, recipient in notify.parent_channels(student):
                if channel not in channels:
                    continue
                text = f"{body}\n- {_institute()}"
                if notify.enqueue(student["id"], channel, recipient, "announcement", text,
                                  f"announce:{aid}:{student['id']}:{channel}", subject=title):
                    queued += 1
                    recipients.add(student["id"])
        execute("UPDATE announcements SET recipients=? WHERE id=?", (len(recipients), aid))
        counts = notify.send_queued() if queued else {"sent": 0, "waiting": 0, "failed": 0}
        audit("announcement.created", "announcement", aid, f"{queued} messages")
        flash(f"Announcement posted to {len(recipients)} parent(s). Messages: {queued} created, "
              f"{counts['sent']} delivered, {counts['waiting']} waiting for provider setup, "
              f"{counts['failed']} failed.", "ok")
        return redirect(url_for("comms.index"))
    return render_template("broadcast.html", batches=batches, channels=notify.CHANNELS)


def _institute():
    from ..db import get_setting
    return get_setting("institute_name", "The Institute")
