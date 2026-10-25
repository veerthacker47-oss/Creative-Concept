# Deployment checklist — Coaching Institute Management System

## Recommended Render deployment

This repository includes `render.yaml`. It configures a Python web service, HTTPS-ready secure cookies, generated secret keys, a one-time first-admin setup token, encrypted website email settings, a health endpoint, and a persistent disk mounted at `/var/data`.

**Important:** a persistent disk requires a paid Render web-service plan. The service is configured as `starter`; check current pricing before confirming deployment. Do not switch to ephemeral free hosting while using SQLite for real student data.

1. Upload the extracted project files to a private GitHub repository. Do not upload `.env`, database files, backups, generated secret keys, or real student data.
2. In Render, create a new Blueprint and connect that repository; Render reads `render.yaml`.
3. Enter `INSTITUTE_NAME` when prompted. Leave email/Twilio/AI environment variables blank unless the institute has set up those services.
4. Wait for the build and `/healthz` check to pass. A healthy process does not mean full application tests have passed.
5. In the Render service's Environment settings, retrieve the generated `INITIAL_SETUP_TOKEN` securely. Open `/setup` on the deployed site and enter it once to create the first administrator. Do not share the token publicly. After setup, the route redirects to login because an administrator exists.
6. Sign in and complete the institute name/address/contact details. Complete all bracketed placeholders in the public policy pages before the institute starts collecting real data.
7. In Settings, configure email using an institute-owned sender account, then send a test message to an address controlled by the institute. The SMTP password is encrypted using `EMAIL_SETTINGS_ENCRYPTION_KEY`; never paste credentials into GitHub issues or chat.
8. Create a backup and verify that it can be downloaded. Establish an off-site backup process; a disk on the same hosting account is not a complete disaster-recovery plan.
9. Test staff roles and ensure a portal account can access only its linked student's records. Use synthetic test data first.
10. Review logs, accessibility, policy text, retention/deletion procedures, consent records, incident response, and applicable legal obligations with the institute before production.

## Important limitations

- GitHub upload alone does not publish the site. A hosting account must be connected and a deployment must succeed.
- Google Search indexing is separate. This is an administrative system and intentionally sends `noindex`; do not index private student-management screens. If the institute needs a public marketing site, create a separate public-facing site.
- A custom domain is optional and must be purchased/connected separately.
- Website email settings can be configured in Admin Settings only when the encryption key exists in the hosting environment. SMS/WhatsApp still require provider credentials in the private environment and successful testing.
- Policy templates contain placeholders and require the institute's real business details and review. This software cannot guarantee legal compliance or zero vulnerabilities.
