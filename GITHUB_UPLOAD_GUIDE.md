# Upload this project to GitHub safely

1. Extract this ZIP. The folder to upload is `coaching-institute/`.
2. Create a new GitHub repository for the institute app.
3. Upload the project files and folders from this folder (not the outer ZIP itself).
4. Keep `.env` and real student data private. `.gitignore` excludes `.env`, `data/`, Python caches and bytecode.
5. After each push, open the repository's **Actions** tab. The automated workflow checks Python syntax and runs the test suite.
6. Only deploy after the workflow passes and you have tested the live site.

## Important

- The workflow has been added, but its first run on GitHub is still required. This bundle was syntax-checked and ZIP-checked; the full test suite could not be run in this build environment because Python dependencies could not be downloaded here.
- No code bundle can guarantee zero errors on every device or hosting provider. Python version, installed dependencies, environment variables, persistent database storage, and provider settings matter.
- Never upload live student records, `.env`, Gmail App Passwords, Twilio tokens, or API keys to a public repository.
- A GitHub repository stores source code; it does not by itself keep the website online or host the production database.

## Online deployment (Render Blueprint)

1. Create a **private** GitHub repository and upload the extracted project files.
2. Wait for GitHub Actions. Do not ignore a failed test or dependency-audit result.
3. In Render, create a **Blueprint** connected to that repository; it will read `render.yaml`.
4. Review the selected `starter` plan and persistent disk cost before approving. The disk is required because this app uses SQLite for student and fee records; an ephemeral filesystem can lose data after a restart/redeploy.
5. Set the `INSTITUTE_NAME` environment value when prompted. Optional message/AI providers can stay unconfigured.
6. Once deployed, retrieve `INITIAL_SETUP_TOKEN` from the private service environment, open `/setup` once, and create the first administrator. Keep the token secret.
7. In Admin → Settings, fill the institute's real legal/contact/retention/refund details and configure SMTP. Send a test email to an account you control.
8. Test student creation, attendance, exams, report cards, portal isolation, backup/restore and all staff roles with synthetic records before using real data.

The app intentionally sends `noindex` because it is an administrative system containing private student data. If the institute wants to appear in Google Search, create a separate public marketing site rather than indexing the private management system.
