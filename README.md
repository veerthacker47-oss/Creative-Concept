# Creative Concept — Coaching Institute Management & Automation System

One integrated Flask + SQLite application for Creative Concept. Owner: Madhav Rajde. Public contact: +91 87587 87474.
Everything is in one project, shares one database, one login system and one design.
It is built to be used from a phone browser.

## Modules

| Area | What it does |
|---|---|
| Students | Register, search, filter, edit, deactivate (never delete), CSV import with row-level errors and preview, CSV export |
| Batches & timetable | Batches with teacher, capacity and monthly fee; weekly timetable; homework |
| Attendance | Mark Present / Absent / Late / Excused per batch per day; "Mark all present" and "mark unmarked present"; optional absence alerts to parents (once per student per day); daily register and monthly report with <75% flags |
| Fees | Invoices, monthly tuition generation (one per student per month), payments with receipt numbers, FIFO allocation, outstanding and overdue lists, printable receipts |
| Reminders | Overdue reminders, max one per family per month per channel |
| Communication | Announcements to all or one batch (email / SMS / WhatsApp), duplicate-post protection, full message history, retry |
| Exams | Exams per batch with subject, maximum marks and passing marks; searchable marks register with per-student save/clear and class save; pass/fail; exam analytics; batch performance analytics with subject averages and recent score changes; printable report cards |
| Staff | Accounts with roles: admin, front office (staff), teacher, accountant; password reset; protection against removing the last admin |
| Dashboard | Live numbers polled every 30 s from `/api/stats`; module shortcuts and quick actions |
| Student / parent portal | Separate read-only login for one linked student; attendance, results, fee balance, invoices, timetable, homework and announcements; staff can create or disable portal accounts |
| Assistant | Read-only: summary, absentees, outstanding, notification status, student lookup. Optional AI for general questions (aggregate numbers only, no names sent) |
| Reports | CSV exports: payments by date range, attendance, marks, students, outstanding |
| Admin | Settings, audit log (every write, login, payment, export), verified nightly backups with download |
| Security | Login throttling (8 failures / 15 min), CSRF tokens on every form, hashed passwords, secure cookies, security headers, role checks on every route |

## Student and parent portal

- Staff with student-edit permission can open **Student & parent portal** from the dashboard/navigation and create a login for an active student.
- Each portal account is linked to exactly one student. Parents/students cannot search for or open another student's records through the portal.
- Give the username and temporary password to the family privately. Portal users can change their password from the portal; staff can disable accounts when access should end.
- Families open `/portal/login`. The portal is read-only; staff continue to manage marks, fees, attendance, homework, timetable and announcements through the administration pages.
- Use HTTPS in production. Accounts should only be created after confirming the correct student record and guardian identity.

## Notification honesty

A message is shown as **sent** only after the email or Twilio provider accepts it.
Until a provider is configured on the server, messages stay **queued** with the reason
("... is not configured on the server"). Retries happen every 5 minutes; after 5 real
failures a message is marked **failed**. Duplicate messages are blocked by a unique key
(for example `absence:<student>:<date>:<channel>`).

## Setup (on your computer or a server)

```bash
cd coaching-institute
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then edit values (keep .env private)
export COOKIE_SECURE=0        # only for http://localhost testing
flask run                     # open http://127.0.0.1:5000 -> first-time setup creates the admin
```

Convenience launchers are included: `./run_local.sh` for Linux/macOS/Termux and `run_local.bat` for Windows. They install the listed Python packages, create `.env` if missing, and start a local-only development server. The first visit opens the administrator setup screen. These scripts require internet access for package installation on first run; they are for local testing, not production hosting.

Run the tests:

```bash
python -m unittest discover -s tests -v
```

## Production

A Render Blueprint is included in `render.yaml`; see `DEPLOYMENT_CHECKLIST.md`. It uses a paid persistent disk for SQLite and backups. Do not deploy a live institute database to an ephemeral filesystem.

```bash
gunicorn --workers 1 --threads 4 --timeout 120 -b 0.0.0.0:8000 wsgi:app
```

Use **one** worker (`-w 1`) with the built-in scheduler, or set `SCHEDULER_ENABLED=0`
and run jobs from cron (the scheduler would otherwise start once per worker):

```cron
30 0 * * * cd /path/to/coaching-institute && .venv/bin/flask run-jobs
```

(00:30 UTC = 06:00 India time.)

Put the app behind HTTPS. Keep `COOKIE_SECURE=1` (the default).

## Data and backups

- Database: `data/institute.db` (or `DATABASE_PATH`). Secret key: `data/secret_key.txt` unless `SECRET_KEY` is set.
- Backups: `data/backups/` every night at 02:00 IST, integrity-checked, newest 30 kept.
- Backups on the same server do not protect against losing that server. Download a copy from **Backups** every week and store it elsewhere.

## Paid services and free alternatives

| Need | Free option | Paid option |
|---|---|---|
| Email to parents | Gmail SMTP with an App Password (limited daily volume); Brevo free tier | Any transactional email service |
| SMS / WhatsApp | Not free to send. Use the in-app history and phone calls for families without email | Twilio (pay per message; trial credits are limited); WhatsApp messages are billed per conversation |
| AI assistant | Built-in commands (summary, absentees, outstanding, find student) need no key | Anthropic API key, billed per use |
| Hosting | Oracle Cloud Always Free VM (persistent disk), or a free PythonAnywhere account (check its outbound-network rules for SMTP/Twilio) | Any small VPS |

Check each provider's current free-tier terms before depending on them. Free hosts that
delete files when they restart (such as many free "web service" plans) will lose the
SQLite database, so only use a host with a persistent disk.

## Developing from an Android phone

- Ask the assistant to make a change, then save the new files in your GitHub repository (GitHub's mobile app or site).
- Your server pulls the latest version and restarts. Use the phone browser for everything else.
- Run `python -m unittest discover -s tests` on the server or in a Python-capable Android app before deploying.

## Changes in this version

See `CHANGES.md` for the full list of changed files and verification notes. The new features still need a live deployment smoke test before the institute relies on them.

## Known limits (honest list)

- A student belongs to one batch at a time (multi-batch enrolment is not built).
- The assistant is read-only. Records are changed through the pages.
- Live numbers refresh every 30 seconds (polling, not push).
- The login throttle is stored in SQLite and works across application restarts. The scheduler runs inside one process, so the included Render configuration intentionally uses one worker. Do not scale the SQLite/disk-backed service to multiple instances.
- Email delivery and Twilio (SMS/WhatsApp) have not been tested against live providers. Configure the provider and send a test message to an address/number controlled by the institute before relying on delivery.
- First public deployment requires the generated `INITIAL_SETUP_TOKEN` for creating the first administrator. Website-based SMTP setup requires `EMAIL_SETTINGS_ENCRYPTION_KEY`, generated by the included Render Blueprint.
- Student record creation/import records a staff acknowledgement that the privacy notice and any required lawful basis/guardian consent were handled separately. This does not itself prove or replace required verified consent.
- Report cards print from the browser (Print → Save as PDF). No separate PDF engine.
- Student photos and online fee payments (gateway) are not included.
- Parent access to multiple siblings in one account is not included; each portal login is linked to one student.
- AI-driven performance insights are intentionally deferred to the next phase; current analytics are deterministic summaries of recorded marks.

## File layout

```
config.py                 settings from environment variables
wsgi.py                   production entry point
app/__init__.py           app factory, security headers, CLI commands
app/db.py                 schema, queries, audit log, settings, backups
app/security.py           login, roles/permissions, CSRF, login throttle
app/jobs.py               scheduled workflows (all idempotent)
app/services/notify.py    notification queue, duplicate protection, providers
app/services/fees.py      ledger and outstanding calculations
app/services/stats.py     dashboard numbers
app/routes/*.py           one file per module
app/templates/*.html      mobile-first pages
app/static/style.css      styles
tests/test_workflows.py   end-to-end tests
```

## Public website and free hosting

A separate public marketing-site starter is in `public-site/`. GitHub Pages can publish that directory free through `.github/workflows/pages.yml`; see `PUBLIC_SITE_DEPLOYMENT.md`. The public site is intentionally separate from the private management application.

**Production warning:** the management app currently uses SQLite and has not been migrated to Supabase/PostgreSQL. Do not enter real student data on an ephemeral free host. Read `PUBLIC_SITE_DEPLOYMENT.md` and `FINAL_REVIEW_STATUS.md` before deployment. The previous paid Render Blueprint was removed so this package will not silently create a paid service or persistent disk.
