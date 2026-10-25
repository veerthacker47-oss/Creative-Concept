# Security, privacy, accessibility and legal-content audit

Review date: 25 October 2026. Static source/configuration review only; not a penetration test, legal opinion or compliance certificate.

## Implemented in this package

- CSRF checks on state-changing requests; password hashing; role permission decorators; request size cap; secure session-cookie defaults; private/no-store dynamic responses.
- Persistent SQLite-backed login throttling with HMAC-pseudonymized throttle keys; atomic first-admin creation and optional one-time setup token for public deployment. Password change/reset increments session versions to invalidate existing sessions.
- Security headers including a stricter same-origin CSP (`script-src 'self'`), frame denial, object denial, restricted base/form actions, MIME sniffing protection, permissions policy, and HSTS on HTTPS requests.
- Website-based SMTP settings for authorized admins with allow-listed SMTP hosts, allowed TLS ports, encrypted-at-rest SMTP password, masked password input, and test-email action.
- Public policy routes; legal/privacy contact and retention/refund settings; stored staff acknowledgement on student create/import.
- External JavaScript files instead of inline scripts/event handlers; skip navigation, focus visibility, many explicit form-label associations, unique literal IDs in checked templates, and measured contrast ratios above 4.5:1 for the checked primary text/status pairs.
- Render blueprint with generated secrets and a persistent disk for SQLite/backups.

## Current findings / boundaries

- **Automated tests:** syntax and direct SQLite checks passed, but full unittest suite and dependency audit could not run here because dependencies could not be downloaded. GitHub Actions must pass before launch.
- **Business-specific policies:** settings must be filled with the institute's real details and actual refund/retention rules. A default warning is shown if refund/retention settings are absent. Legal review remains necessary.
- **Consent:** the application records a staff acknowledgement that the notice/lawful basis/required consent has been handled; it does not itself collect or verify a parent's consent. Add a separate consent evidence workflow if the institute's legal review says it is required.
- **Children's data:** institute must determine applicable notices, guardian consent/exemptions, purpose, retention, and rights workflows under applicable law.
- **Access control:** decorators exist but every route/object must be tested with distinct roles. Especially verify that portal accounts can only read their linked student's data and that CSVs/backups cannot be accessed by unauthorized roles.
- **MFA/recovery:** administrator MFA and a secure password-reset/account-recovery flow are not confirmed as implemented. Consider them before production.
- **Rate limiting:** SQLite throttle is persistent/shared only for instances using the same database. It is not a substitute for edge/WAF protection against distributed attacks; use one disk-backed instance as configured.
- **Database/storage:** SQLite on a Render persistent disk requires a single service instance and paid disk plan. Test backup/restore and keep an off-site protected backup. Do not use ephemeral filesystem for real records.
- **SMTP:** encryption depends on the private `EMAIL_SETTINGS_ENCRYPTION_KEY`. Keep it stable and secret; rotating it without re-encrypting stored values makes them unreadable. Test with an institute-controlled recipient. Provider acceptance is not final delivery.
- **SMS/WhatsApp/AI:** still depend on optional provider secrets and account permissions; do not claim configured or tested until verified.
- **Accessibility:** many labels were associated with controls, but this is not a full WCAG audit. Check keyboard-only use, contrast, zoom/reflow, screen readers, errors, focus order and mobile behavior.
- **Cookies/third parties:** checked templates contain no analytics pixels or third-party iframe embeds and use essential session cookies. No non-essential cookie banner is needed for the checked code alone; recheck hosting/CDN/scripts at deployment and add consent before any non-essential tracking where required.
- **Images/copyright/reviews:** no `<img>` template assets or testimonial/review markup were found. If marketing content or images are added, use licensed assets, provide accurate alt text, and never invent testimonials or claims.
- **Google:** the admin app is intentionally marked `noindex`. Do not submit private student-management screens to Search. Google Play policies apply separately if an Android app is distributed there.

## Before production

1. GitHub Actions must pass unit tests and dependency audit; resolve every critical/high issue.
2. Deploy to a private repository and paid disk-backed host; verify health check, HTTPS, cookies, setup token, persistent database and backups.
3. Complete settings and public policies with real institute facts, retention/refund terms, grievance details, actual processors and support contacts.
4. Complete role matrix and portal isolation tests; test imports, exports, backup access, password changes, login throttling and SMTP configuration.
5. Test backup restore and establish off-site protected backups.
6. Perform a scoped authorized security assessment and accessibility review.
7. Review current Indian law and applicable commencement notifications with qualified counsel; document breach response and incident contacts.

## Official references

- https://www.indiacode.nic.in/indiacode/handle/123456789/22037?view_type=browse
- https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?pageTitle=Digital-Personal-Data-Protection-Rules-2025
- https://www.cert-in.org.in/Directions70B.jsp
- https://support.google.com/googleplay/android-developer/answer/18258653?hl=en-IN
- https://developers.google.com/search/docs/essentials/spam-policies
- https://render.com/docs/blueprint-spec
- https://render.com/docs/disks
