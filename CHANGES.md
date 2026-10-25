# Changes in this version

## Upgrade notes (existing installs)
- Database: the `exams` table gets two new nullable columns, `subject` and `pass_marks`. They are added automatically the first time the app starts. No rows are changed or deleted. Existing exams use the institute pass percentage until you set a passing mark.
- Attendance reports now count only records saved for the selected batch, so a student who moved batches no longer has the previous batch's records counted in this batch's monthly figures.
- Back up `data/` before upgrading (Backups page, or `flask backup-db`).

## What changed
- **Dashboard**: attendance % for today, recent activity (administrators), module navigation tiles. Login/logout are kept out of activity.
- **Attendance**: Mark all present (overrides existing marks, with confirmation), Mark unmarked present, Present/Absent/Late/Excused counters, an option to send absence alerts (ticked by default), a daily register view, and saving now requires the `attendance.mark` permission on the server, not only the view permission.
- **Exams & marks**: subject and passing marks on exams, pass/fail per student, passing marks checked against the maximum, `nan` and `inf` rejected, CSV export includes Pass/Fail.
- **Report cards**: subject column, pass/fail per exam, subject-wise totals, and a Report cards page listing each batch's students.
- **Notifications**: SMTP port 465 (implicit SSL) supported; a clear message when SMTP_FROM / SMTP_USER are missing; announcements refused when no channel is ticked; setup instructions on the Settings page for Gmail App Passwords and Twilio.
- **Tests**: `tests/test_fixes.py` (26 tests) added to the existing 7.

## Changed files
- app/db.py (schema column + additive migration)

- app/routes/attendance.py, app/routes/exams.py, app/routes/dashboard.py, app/routes/comms.py
- app/services/notify.py, app/services/stats.py
- app/templates/base.html, dashboard.html, attendance.html, attendance_report.html,
  exams.html, exam_detail.html, report_card.html, report_cards.html (new), admin_settings.html
- app/static/style.css
- tests/test_fixes.py (new)
- README.md, CHANGES.md (new)

## Not changed
.env, .env.example values, data/, backups, student records, secret keys.


## Extended institute edition (new)
- **Priority 1 — Marks entry:** searchable marks register; save a single student's marks without changing other rows; save all entered marks; clear a saved mark explicitly; clearer validation and progress indicator.
- **Priority 2 — Performance analytics:** batch-wide average scores, subject averages, recent score movement, and supportive teacher check-in flags when the latest result drops by at least 10 percentage points. Flags are prompts for review, not automatic judgements.
- **Priority 3 — Fees:** retained the existing invoice/payment ledger, monthly fee generation, receipt and overdue-report workflows; balances are now visible in the family portal.
- **Priority 4 — Student / parent portal:** separate, read-only login linked to one active student; shows attendance, recent exam results, fee overview, timetable, homework and announcements. Staff can create/disable accounts; passwords are hashed and portal login uses the shared login throttling.
- **Priority 5 — Institute operations:** retained batch timetables, homework and announcements, now visible to families through their portal; upgraded navigation and mobile-responsive interface across admin and family pages.
- **Priority 6 — AI insights:** intentionally deferred as requested.
- Added `portal_accounts` table (additive migration via `CREATE TABLE IF NOT EXISTS`); existing student, fee, attendance and marks data are not deleted or rewritten.
- Added tests for individual marks saving/clearing, portal record isolation and performance analytics. Test execution is pending because this environment could not install Flask dependencies (network/DNS unavailable); Python syntax and SQLite schema checks are run separately.
