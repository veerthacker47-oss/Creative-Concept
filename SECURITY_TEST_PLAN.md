# Security and release test plan

## Automated checks (GitHub Actions)

- Install pinned/ranged dependencies from `requirements.txt`.
- Run `pip-audit -r requirements.txt` and resolve reported advisories.
- Compile all Python files.
- Run `python -m unittest discover -s tests -v`.
- New regression tests cover setup token enforcement, database-backed login throttle persistence, encrypted SMTP setting reads and strict script CSP.

## Manual acceptance tests — synthetic data only

- Login throttling remains active after app restart; invalid first-setup tokens are rate-limited; first-admin setup cannot create a second initial account.
- Test admin, staff, teacher, accountant, logged-out visitor, student portal and parent portal against every relevant route. Confirm object-level isolation for student IDs, reports, CSV exports, fees, attendance, marks, announcements and backups.
- Test CSRF protection for all state-changing forms, secure cookies over HTTPS, session expiry, password change/reset invalidation of other sessions, disabled users and logout.
- Test malformed/oversized CSV files, duplicate admission numbers, CSV formula injection, request limits, and backup path validation.
- Configure SMTP through Admin Settings; try invalid host, invalid port, blank password, correct password, wrong password and a test recipient controlled by the institute. Confirm password is never rendered or returned.
- Confirm backups are written to persistent storage, downloadable only by authorized users, integrity-checked, and restorable; keep an off-site encrypted copy.
- Confirm the host has no debug mode, no public `.env`, no public database/backups, HTTPS, persistent disk, private secrets and current dependencies.
- Inspect deployed source/HTML for external trackers, embeds, unexpected requests and personal-data leakage. Confirm `noindex` remains on the admin system.
- Accessibility: use keyboard only; inspect focus order/visible focus; check labels with a screen reader; test contrast, errors, zoom/reflow, mobile width, and browser print flows.
- Policy review: complete institute identity, privacy/grievance contact, retention schedule, actual refund terms, processor list, child-data process, data request/deletion procedure and incident-response contacts.

## Evidence required before launch

Save a copy of green GitHub Actions results, dependency-audit output, role-isolation test results, SMTP test result, backup/restore test, policy sign-off, accessibility checklist, and security-assessment findings. Do not add real student records until high/critical findings are resolved.


## Owner-only financial/administrative access
- Only the `admin` role (labelled `Owner / Administrator`) has `fees.edit` and `settings.manage`.
- `staff`, `teacher`, and `accountant` do not have `fees.edit` or `settings.manage`; this is enforced server-side by permission decorators, not only by hiding interface buttons.
- Regression tests assert this role policy. Review any future role changes before deploying.
