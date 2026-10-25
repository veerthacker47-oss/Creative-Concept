"""Public legal/information pages. Review placeholders with the institute before launch."""
from flask import Blueprint, current_app, render_template

from ..db import get_setting

bp = Blueprint("legal", __name__)

PAGES = {
    "privacy": {
        "title": "Privacy Policy",
        "updated": "25 October 2026",
        "sections": [
            ("Who is responsible", "[Institute legal/business name] is responsible for personal information handled through this website. Contact: [privacy contact email and phone]."),
            ("Information we may handle", "Depending on which features the institute uses, records may include student and guardian names, contact details, enrolment/batch information, attendance, marks, fee records, messages, staff account details, and security/audit events. Do not enter information that is not needed for the institute's stated purpose."),
            ("Why information is used", "Information is used to administer enrolment, classes, attendance, examinations, fees, reports, account access, and communications requested or authorised by the institute. The institute must identify and document an appropriate lawful basis for each use."),
            ("Sharing and service providers", "Information may be processed by the hosting provider and any email, SMS, WhatsApp, backup, or AI provider that the institute deliberately configures. Identify actual providers, their purposes, and applicable transfer/retention terms before launch. This version does not intentionally include analytics or advertising trackers."),
            ("Retention, access and security", "The institute should retain information only as long as necessary for its documented purposes and legal obligations, restrict access by role, maintain protected backups, and securely delete data when no longer needed. No online system can promise absolute security."),
            ("Rights and requests", "For access, correction, deletion, grievance, or privacy questions, contact [privacy contact]. The institute must publish a working contact and process requests within applicable legal timelines."),
            ("Children's information", "Student records may concern children. The institute must determine and meet applicable requirements for parent/guardian notice, consent where required, permitted processing, and children's data under Indian law before using this system in production."),
        ],
    },
    "terms": {
        "title": "Terms and Conditions",
        "updated": "25 October 2026",
        "sections": [
            ("Service operator", "This system is operated by [Institute legal/business name]. Contact: [business email/phone/address]."),
            ("Permitted use", "Authorised users may use the system only for legitimate institute administration and must keep account credentials private, use strong unique passwords, and report suspected unauthorised access promptly."),
            ("Accuracy and responsibility", "The institute is responsible for checking student records, attendance, marks, fee entries, recipients, and reports before relying on them or sending communications. Automated calculations and notifications should be reviewed."),
            ("Availability and third parties", "Availability may depend on hosting and configured service providers. Features such as email, SMS, WhatsApp, backups, or AI are available only when configured and successfully tested. Do not describe an untested feature as guaranteed."),
            ("Changes and contact", "The institute should describe its support process, service hours, and how material terms changes are communicated. Contact: [business contact]. Obtain appropriate legal review before publication."),
        ],
    },
    "cookies": {
        "title": "Cookies Policy",
        "updated": "25 October 2026",
        "sections": [
            ("Current use", "This application uses an essential Flask session cookie for login/session security. The code review did not find configured Google Analytics, advertising pixels, or third-party iframe embeds in the application templates checked for this release."),
            ("Essential cookies", "Essential session cookies support authentication and protected forms. They are not used by this release for advertising profiling. Blocking cookies may prevent login and other protected features from working."),
            ("Optional tracking", "Do not add analytics, advertising pixels, non-essential cookies, or third-party embeds without updating this notice and implementing an appropriate consent choice before those technologies run where required by law."),
            ("Questions", "Contact [privacy contact email]. Re-check the deployed site and any hosting/provider scripts before launch; this page reflects the code reviewed, not every browser extension or hosting-level log."),
        ],
    },
    "refund": {
        "title": "Refund Policy",
        "updated": "25 October 2026",
        "sections": [
            ("Policy owner", "This policy must be completed and approved by [Institute legal/business name]. Contact: [business contact]."),
            ("Fees and refunds", "The institute must insert its actual rules for admission fees, tuition fees, cancellations, missed classes, duplicate payments, refund eligibility, deductions (if any), processing timelines, and the method for requesting a refund. Do not publish invented terms."),
            ("How to request help", "Contact [fees/refunds email or phone] with the student's admission reference, payment date, amount, and transaction reference. Avoid sending full card details, passwords, or unnecessary identity documents."),
            ("Before publication", "Confirm this policy matches the institute's enrolment agreement and applicable consumer-protection requirements. This template is not a substitute for legal review."),
        ],
    },
}


def _page(key):
    """Fill factual business fields from administrator settings; keep unknown legal terms flagged."""
    import copy
    page = copy.deepcopy(PAGES[key])
    institute = get_setting("legal_business_name", "") or get_setting("institute_name", "") or current_app.config["INSTITUTE_NAME"]
    address = get_setting("institute_address", "") or "Not configured by the institute"
    phone = get_setting("privacy_contact_phone", "") or get_setting("institute_phone", "") or "Not configured by the institute"
    email = get_setting("privacy_contact_email", "") or get_setting("institute_email", "") or "Not configured by the institute"
    grievance = get_setting("grievance_contact", "") or f"Email: {email}; Phone: {phone}"
    retention = get_setting("data_retention_policy", "") or "The institute has not published a specific retention schedule yet. Contact the institute before submitting new personal data."
    refund = get_setting("refund_policy_terms", "") or "The institute has not completed its refund and cancellation terms. Contact the institute before paying fees; this page is not a statement that refunds are always or never available."
    replacements = {
        "[Institute legal/business name]": institute,
        "[privacy contact email and phone]": f"Email: {email}; Phone: {phone}",
        "[privacy contact email]": email,
        "[privacy contact]": grievance,
        "[business email/phone/address]": f"Email: {email}; Phone: {phone}; Address: {address}",
        "[business contact]": grievance,
        "[fees/refunds email or phone]": f"Email: {email}; Phone: {phone}",
    }
    for index, (heading, body) in enumerate(page["sections"]):
        for old, value in replacements.items():
            body = body.replace(old, value)
        if heading == "Retention, access and security":
            body = retention + " Access should be limited by role, backups should be protected and tested, and records should be securely deleted when no longer needed. No online system can promise absolute security."
        if heading == "Fees and refunds":
            body = refund
        page["sections"][index] = (heading, body)
    return page


@bp.route("/privacy-policy")
def privacy_policy():
    return render_template("legal_page.html", page=_page("privacy"))


@bp.route("/terms")
def terms():
    return render_template("legal_page.html", page=_page("terms"))


@bp.route("/cookies-policy")
def cookies_policy():
    return render_template("legal_page.html", page=_page("cookies"))


@bp.route("/refund-policy")
def refund_policy():
    return render_template("legal_page.html", page=_page("refund"))
