"""Fee ledger logic. Payments are applied oldest-due-first (FIFO), so balances are always consistent."""
from ..db import query
from ..utils import today_local


def student_ledger(student_id):
    today = today_local()
    invoices = query(
        "SELECT * FROM invoices WHERE student_id=? AND cancelled=0 ORDER BY due_date, id",
        (student_id,),
    )
    payments = query(
        "SELECT * FROM payments WHERE student_id=? ORDER BY paid_on, id", (student_id,)
    )
    paid_total = sum(p["amount_paise"] for p in payments)
    remaining = paid_total
    rows, total_due = [], 0
    for inv in invoices:
        applied = min(inv["amount_paise"], remaining)
        remaining -= applied
        balance = inv["amount_paise"] - applied
        total_due += inv["amount_paise"]
        if balance == 0:
            status = "paid"
        elif applied > 0:
            status = "partial"
        else:
            status = "unpaid"
        item = dict(inv)
        item.update(
            paid=applied,
            balance=balance,
            status=status,
            overdue=balance > 0 and inv["due_date"] < today,
        )
        rows.append(item)
    return {
        "invoices": rows,
        "payments": [dict(p) for p in payments],
        "total_due": total_due,
        "total_paid": paid_total,
        "outstanding": total_due - paid_total,
    }


def outstanding_report(batch_id=None):
    """Active students with a positive balance, largest balance first."""
    sql = (
        "SELECT s.id, s.admission_no, s.first_name, s.last_name, s.parent_name,"
        " s.parent_phone, s.parent_email, b.name AS batch_name, b.id AS batch_id"
        " FROM students s LEFT JOIN batches b ON b.id = s.batch_id WHERE s.status='active'"
    )
    args = ()
    if batch_id:
        sql += " AND s.batch_id=?"
        args = (batch_id,)
    result = []
    for s in query(sql, args):
        ledger = student_ledger(s["id"])
        if ledger["outstanding"] <= 0:
            continue
        open_invoices = [i for i in ledger["invoices"] if i["balance"] > 0]
        result.append({
            **dict(s),
            "outstanding": ledger["outstanding"],
            "overdue_amount": sum(i["balance"] for i in open_invoices if i["overdue"]),
            "oldest_due": open_invoices[0]["due_date"] if open_invoices else None,
            "has_overdue": any(i["overdue"] for i in open_invoices),
        })
    result.sort(key=lambda r: -r["outstanding"])
    return result


def total_outstanding():
    return sum(r["outstanding"] for r in outstanding_report())
