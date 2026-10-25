# Free public website and Google Search setup

This repository now has two separate parts:

- `public-site/`: a static public marketing-site starter. GitHub Pages can host it free from a public repository.
- `app/`: the private Flask coaching-management application. It contains student, parent, attendance, exam and fee data; do not publish its routes as a public static site and do not remove its authentication/noindex protections.

## Publish the public site

1. Replace all starter text in `public-site/index.html` with verified institute details. Do not invent results, qualifications, testimonials, fees or addresses.
2. In `public-site/robots.txt` and `public-site/sitemap.xml`, replace `YOUR-GITHUB-USERNAME` and `YOUR-REPO` with the actual GitHub Pages URL. Confirm the URL after Pages is enabled.
3. Upload the repository to GitHub. Use a public repository only after confirming it contains no secrets, `.env`, database files, backups, student data, or credentials.
4. In GitHub repository Settings → Pages, set the publishing source to **GitHub Actions**.
5. Push to the `main` branch. The `Publish public information site` workflow publishes only the `public-site/` directory.
6. Open Google Search Console, verify the published URL, submit `/sitemap.xml`, and request indexing of the homepage. Google decides whether and when to index pages; submission does not guarantee ranking or immediate inclusion.

## Database and dynamic app warning

The current Flask app uses SQLite directly. It has **not** been migrated to Supabase/PostgreSQL in this package. Do not deploy the student-management app on a host with ephemeral storage and enter real student data: local SQLite files can be lost on restart/redeploy. Render's free web services have ephemeral filesystems and spin down after inactivity. Supabase Free offers PostgreSQL but can pause projects after one week of inactivity and does not include automatic backups on the Free plan. Before production, either complete and test a proper PostgreSQL migration (including schema, transactions, migrations, backups and restore) or choose a host with persistent storage and a backup plan.

The public marketing site can be hosted free independently; this does not make the private Flask application production-ready.


## Verified public details
- Institute: Creative Concept
- Owner: Madhav Rajde
- Public phone for fee and administration enquiries: +91 87587 87474
- Email and physical address are intentionally omitted until verified details are provided.
