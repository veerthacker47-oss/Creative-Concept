"""Administrative assistant. Read-only: it answers questions and points to pages; it never changes records."""
import json
import re
import urllib.error
import urllib.request

from flask import Blueprint, current_app, render_template, request, session, redirect, url_for

from ..db import audit, query
from ..security import permission_required
from ..services.fees import outstanding_report
from ..services.stats import collect_stats
from ..utils import fmt_money, today_local

bp = Blueprint("assistant", __name__, url_prefix="/assistant")

HISTORY_KEEP = 6

HELP_TEXT = (
    "I can answer read-only questions. Try:\n"
    "• 'summary' – today's key numbers\n"
    "• 'who is absent today' – absentees for today\n"
    "• 'outstanding fees' – largest balances\n"
    "• 'notifications' – queued and failed messages\n"
    "• 'find <name or admission no>' – look up a student\n"
    "With an AI key configured, you can also ask free-form questions about the institute. "
    "I cannot change records; use the pages in the menu for that."
)

SYSTEM_PROMPT = (
    "You are the administrative assistant for a coaching institute. You receive only aggregate "
    "statistics. Answer briefly and practically. You cannot change any records; if asked to "
    "change data, explain which page to use. Never invent figures that are not in the snapshot."
)


def _rupees(paise):
    return fmt_money(paise)


def _summary():
    s = collect_stats()
    return (
        f"Active students: {s['active_students']} in {s['batches']} batches.\n"
        f"Today ({s['today']}): {s['present_today']} present, {s['absent_today']} absent, "
        f"{s['late_today']} late.\n"
        f"Collected this month: {_rupees(s['collected_this_month_paise'])}. "
        f"Outstanding: {_rupees(s['outstanding_paise'])} ({s['overdue_students']} students overdue).\n"
        f"Notifications: {s['queued_notifications']} queued, {s['failed_notifications']} failed, "
        f"{s['sent_last_24h']} sent in the last 24 hours."
    )


def _absentees():
    rows = query(
        "SELECT s.first_name, s.last_name, s.admission_no, b.name AS batch_name"
        " FROM attendance a JOIN students s ON s.id=a.student_id"
        " LEFT JOIN batches b ON b.id=s.batch_id WHERE a.att_date=? AND a.status='absent'"
        " ORDER BY b.name, s.first_name", (today_local(),))
    if not rows:
        return "No absences recorded today (or attendance has not been marked yet)."
    lines = [f"- {r['first_name']} {r['last_name'] or ''} ({r['admission_no']}), {r['batch_name'] or 'no batch'}"
             for r in rows[:50]]
    more = f"\n…and {len(rows) - 50} more." if len(rows) > 50 else ""
    return f"{len(rows)} absent today:\n" + "\n".join(lines) + more


def _outstanding():
    rows = outstanding_report()
    if not rows:
        return "No outstanding balances."
    total = sum(r["outstanding"] for r in rows)
    lines = [f"- {r['first_name']} {r['last_name'] or ''} ({r['admission_no']}): "
             f"{_rupees(r['outstanding'])}" + (" [overdue]" if r["has_overdue"] else "")
             for r in rows[:10]]
    return f"{len(rows)} students owe {_rupees(total)} in total. Largest balances:\n" + "\n".join(lines)


def _notifications():
    rows = query("SELECT status, COUNT(*) AS n FROM notifications GROUP BY status")
    if not rows:
        return "No notifications have been created yet."
    parts = ", ".join(f"{r['n']} {r['status']}" for r in rows)
    return (f"Notifications: {parts}. Queued messages wait until the email/SMS provider is configured "
            "on the server; they are never shown as sent until the provider accepts them.")


def _find(term):
    term = term.strip()
    if len(term) < 2:
        return "Give me at least two characters to search."
    rows = query(
        "SELECT s.id, s.first_name, s.last_name, s.admission_no, s.status, b.name AS batch_name"
        " FROM students s LEFT JOIN batches b ON b.id=s.batch_id"
        " WHERE s.first_name LIKE ? OR s.last_name LIKE ? OR s.admission_no LIKE ? LIMIT 10",
        (f"%{term}%", f"%{term}%", f"%{term}%"))
    if not rows:
        return f"No students match '{term}'."
    return "\n".join(
        f"- {r['first_name']} {r['last_name'] or ''} · {r['admission_no']} · {r['batch_name'] or 'no batch'}"
        f" · {r['status']} (open /students/{r['id']})" for r in rows)


def _ask_ai(question):
    key = current_app.config["ANTHROPIC_API_KEY"]
    if not key:
        return None
    absent_today = query(
        "SELECT COUNT(*) AS n FROM attendance WHERE att_date=? AND status='absent'",
        (today_local(),), one=True)["n"]
    snapshot = _summary() + f"\nAbsentees today: {absent_today}"
    body = json.dumps({
        "model": current_app.config["ANTHROPIC_MODEL"],
        "max_tokens": 500,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"Snapshot:\n{snapshot}\n\nQuestion: {question}"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body, method="POST",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return f"The AI service rejected the request (HTTP {exc.code}). Check the API key and model name."
    except Exception as exc:
        return f"The AI service could not be reached: {exc}"
    text = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
    return text.strip() or "The AI service returned an empty answer."


def answer(question):
    q = question.lower().strip()
    if not q:
        return HELP_TEXT
    if q in ("help", "?", "commands"):
        return HELP_TEXT
    if re.search(r"\b(absent|absentee|absentees)\b", q):
        return _absentees()
    if re.search(r"\b(outstanding|dues?|pending fee|balance|unpaid)\b", q):
        return _outstanding()
    if re.search(r"\b(notification|notifications|queued|failed messages?)\b", q):
        return _notifications()
    if re.search(r"\b(summary|stats|statistics|dashboard|overview)\b", q):
        return _summary()
    m = re.match(r"^(find|search|lookup|look up)\s+(.+)$", q)
    if m:
        return _find(m.group(2))
    ai = _ask_ai(question)
    if ai is not None:
        return ai
    return ("I did not recognise that command, and the AI assistant is not configured on this "
            "server (no ANTHROPIC_API_KEY).\n\n" + HELP_TEXT)


@bp.route("/", methods=["GET", "POST"])
@permission_required("assistant.use")
def index():
    history = session.get("assistant_history", [])
    if request.method == "POST":
        question = (request.form.get("question") or "").strip()[:500]
        reply = answer(question)
        history = (history + [{"q": question, "a": reply}])[-HISTORY_KEEP:]
        session["assistant_history"] = history
        audit("assistant.query", "assistant", None, question[:200])
        return redirect(url_for("assistant.index"))
    return render_template("assistant.html", history=history,
                           ai_enabled=bool(current_app.config["ANTHROPIC_API_KEY"]))


@bp.route("/clear", methods=["POST"])
@permission_required("assistant.use")
def clear():
    session.pop("assistant_history", None)
    return redirect(url_for("assistant.index"))
