"""SQLite access, schema, audit log, settings and backups."""
import os
import sqlite3
from datetime import datetime

from flask import g, current_app, has_request_context, request, session

SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_attempts (
    id INTEGER PRIMARY KEY,
    bucket_hash TEXT NOT NULL,
    attempted_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_bucket_time ON auth_attempts(bucket_hash, attempted_at);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin','staff','teacher','accountant')),
    phone TEXT,
    designation TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    session_version INTEGER NOT NULL DEFAULT 0,
    last_login TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS portal_accounts (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('student','parent')),
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    active INTEGER NOT NULL DEFAULT 1,
    session_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_portal_accounts_student ON portal_accounts(student_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id TEXT,
    details TEXT,
    ip TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    subject TEXT,
    teacher_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    capacity INTEGER NOT NULL DEFAULT 40,
    monthly_fee_paise INTEGER NOT NULL DEFAULT 0 CHECK (monthly_fee_paise >= 0),
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY,
    admission_no TEXT NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT,
    gender TEXT,
    dob TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    parent_name TEXT NOT NULL,
    parent_phone TEXT,
    parent_email TEXT,
    batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive','left')),
    joined_on TEXT,
    privacy_notice_acknowledged INTEGER NOT NULL DEFAULT 0,
    privacy_notice_acknowledged_at TEXT,
    privacy_notice_version TEXT,
    privacy_notice_acknowledged_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_students_batch ON students(batch_id);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL,
    att_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('present','absent','late','excused')),
    marked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT,
    UNIQUE (student_id, att_date)
);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(att_date);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    description TEXT NOT NULL,
    period TEXT,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    due_date TEXT NOT NULL,
    cancelled INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, period)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    method TEXT NOT NULL DEFAULT 'cash',
    reference TEXT,
    paid_on TEXT NOT NULL,
    receipt_no TEXT NOT NULL UNIQUE,
    recorded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_payments_student ON payments(student_id);

CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL,
    channels TEXT NOT NULL DEFAULT '',
    recipients INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    student_id INTEGER REFERENCES students(id) ON DELETE SET NULL,
    channel TEXT NOT NULL CHECK (channel IN ('email','sms','whatsapp')),
    recipient TEXT,
    kind TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','sent','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    provider_id TEXT,
    dedupe_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);

CREATE TABLE IF NOT EXISTS timetable (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    subject TEXT NOT NULL,
    room TEXT
);

CREATE TABLE IF NOT EXISTS homework (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    details TEXT,
    due_date TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    exam_date TEXT,
    max_marks REAL NOT NULL CHECK (max_marks > 0),
    subject TEXT,
    pass_marks REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (name, batch_id)
);

CREATE TABLE IF NOT EXISTS marks (
    id INTEGER PRIMARY KEY,
    exam_id INTEGER NOT NULL REFERENCES exams(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE RESTRICT,
    marks REAL,
    absent INTEGER NOT NULL DEFAULT 0,
    remarks TEXT,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (exam_id, student_id)
);
"""


def connect(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    try:
        # Student, attendance, marks and fee data should not be world-readable on POSIX hosts.
        os.chmod(path, 0o600)
    except OSError:
        pass
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _migrate(conn):
    """Additive, non-destructive upgrades for databases created by earlier versions."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(exams)").fetchall()}
    if "subject" not in cols:
        conn.execute("ALTER TABLE exams ADD COLUMN subject TEXT")
    if "pass_marks" not in cols:
        conn.execute("ALTER TABLE exams ADD COLUMN pass_marks REAL")
    student_cols = {r[1] for r in conn.execute("PRAGMA table_info(students)").fetchall()}
    if "privacy_notice_acknowledged" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN privacy_notice_acknowledged INTEGER NOT NULL DEFAULT 0")
    if "privacy_notice_acknowledged_at" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN privacy_notice_acknowledged_at TEXT")
    if "privacy_notice_version" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN privacy_notice_version TEXT")
    if "privacy_notice_acknowledged_by" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN privacy_notice_acknowledged_by INTEGER REFERENCES users(id) ON DELETE SET NULL")
    user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "session_version" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")
    portal_cols = {r[1] for r in conn.execute("PRAGMA table_info(portal_accounts)").fetchall()}
    if "session_version" not in portal_cols:
        conn.execute("ALTER TABLE portal_accounts ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    rows = get_db().execute(sql, args).fetchall()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    """Run a write statement and commit. Returns the cursor (use .lastrowid / .rowcount)."""
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur


def audit(action, entity=None, entity_id=None, details=""):
    user_id = session.get("user_id") if has_request_context() else None
    ip = request.remote_addr if has_request_context() else None
    execute(
        "INSERT INTO audit_log(user_id, action, entity, entity_id, details, ip) VALUES (?,?,?,?,?,?)",
        (user_id, action, entity,
         None if entity_id is None else str(entity_id),
         (details or "")[:500], ip),
    )


def get_setting(key, default=""):
    row = query("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return row["value"] if row and row["value"] is not None else default


def set_setting(key, value):
    execute(
        "INSERT INTO settings(key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def create_backup(path, backup_dir, keep):
    """Copy the live database to a timestamped file using SQLite's online backup API."""
    os.makedirs(backup_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(backup_dir, f"institute-{stamp}.db")
    src = connect(path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
        integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if integrity != "ok":
        os.remove(dest)
        raise RuntimeError(f"Backup failed integrity check: {integrity}")
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    files = sorted(
        f for f in os.listdir(backup_dir)
        if f.startswith("institute-") and f.endswith(".db")
    )
    if keep > 0:
        for old in files[:-keep]:
            os.remove(os.path.join(backup_dir, old))
    return dest
