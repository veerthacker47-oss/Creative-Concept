from flask import Blueprint, jsonify, render_template

from ..db import query
from ..security import has_perm, login_required
from ..services.stats import collect_stats

bp = Blueprint("dashboard", __name__)



def _recent_activity():
    if not has_perm("audit.view"):
        return []
    rows = query(
        "SELECT a.action, a.details, a.created_at, u.full_name FROM audit_log a"
        " LEFT JOIN users u ON u.id = a.user_id"
        " WHERE a.action NOT LIKE 'auth.%' AND a.action NOT LIKE 'login%'"
        " ORDER BY a.id DESC LIMIT 8")
    return [dict(r) for r in rows]


@bp.route("/")
@login_required
def index():
    return render_template("dashboard.html", stats=collect_stats(), activity=_recent_activity())


@bp.route("/api/stats")
@login_required
def api_stats():
    """Polled by the dashboard every 30 seconds for live numbers."""
    return jsonify(collect_stats())
