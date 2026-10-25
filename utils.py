"""Shared helpers: money (stored as paise), dates, phone numbers, grades, CSV."""
import csv
import io
import re
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from flask import Response, current_app


def tz():
    return ZoneInfo(current_app.config["TIMEZONE"])


def now_local():
    return datetime.now(tz())


def today_local():
    return now_local().date().isoformat()


def month_of(day_iso):
    return day_iso[:7]


def parse_date(value):
    """Return an ISO date string (YYYY-MM-DD) or None if the value is not a valid date."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_money(text):
    """Convert rupee text such as '1,500.50' into integer paise. Raises ValueError."""
    cleaned = (text or "").replace(",", "").replace("₹", "").strip()
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("Enter a valid amount in rupees.")
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    paise = int((amount * 100).to_integral_value())
    return paise


def fmt_money(paise):
    """Format integer paise as Indian-style rupees, e.g. ₹1,23,456.00."""
    paise = paise or 0
    sign = "-" if paise < 0 else ""
    whole, frac = f"{abs(paise) / 100:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}₹{whole}.{frac}"


def fmt_date(value):
    if not value:
        return "—"
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return value


def normalize_phone(raw):
    """Keep digits and a leading +. A bare 10-digit number is treated as Indian (+91)."""
    if not raw:
        return ""
    raw = raw.strip()
    digits = re.sub(r"[^\d]", "", raw)
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    return digits


def valid_email(value):
    return bool(value) and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value) is not None


def grade_for(percent):
    if percent is None:
        return "—"
    if percent >= 90:
        return "A+"
    if percent >= 80:
        return "A"
    if percent >= 70:
        return "B"
    if percent >= 60:
        return "C"
    if percent >= 50:
        return "D"
    if percent >= 35:
        return "E"
    return "F"


def new_receipt_no():
    year = now_local().year
    return f"RCP{year}-{secrets.token_hex(4).upper()}"


def _spreadsheet_safe(value):
    """Neutralize formula-like text before exporting user data to spreadsheet CSV."""
    if not isinstance(value, str):
        return value
    # Spreadsheet programs may execute cells beginning with formula/control characters.
    stripped = value.lstrip("\ufeff\t\r\n ")
    if stripped.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def csv_response(filename, headers, rows):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow([_spreadsheet_safe(value) for value in headers])
    for row in rows:
        writer.writerow([_spreadsheet_safe(value) for value in row])
    return Response(
        buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
