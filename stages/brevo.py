from pathlib import Path

from config import BREVO_API_KEY, BREVO_BASE_URL, SENDER_EMAIL, SENDER_NAME
from models import Contact
from utils.http import request_with_retry
from utils.logging import error, info, success, warn

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "email.html"


def _load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _render_template(contact: Contact) -> tuple[str, str]:
    html = _load_template()
    replacements = {
        "{{first_name}}": contact.first_name or "there",
        "{{company_name}}": contact.company_name or contact.company_domain,
        "{{job_title}}": contact.job_title or "your role",
    }
    for key, value in replacements.items():
        html = html.replace(key, value)

    text = (
        f"Hi {contact.first_name or 'there'},\n\n"
        f"I'm Sereena — I build automation tools that help teams scale B2B outreach "
        f"without manual work.\n\n"
        f"I came across {contact.company_name or contact.company_domain} while "
        f"researching companies in your space, and given your role as "
        f"{contact.job_title or 'your role'}, I thought this might be relevant.\n\n"
        f"I've built a fully automated pipeline that takes a single company domain, "
        f"finds lookalike companies, surfaces decision-makers, resolves verified work "
        f"emails, and sends personalized outreach — all with zero manual handoffs.\n\n"
        f"Would you be open to a quick 15-minute call this week to see if this could "
        f"help your team?\n\n"
        f"Best,\nSereena Thomas\nhello@sereena.live"
    )
    return html, text


def send_outreach_emails(contacts: list[Contact]) -> tuple[int, int]:
    if not BREVO_API_KEY:
        raise ValueError("BREVO_API_KEY is not set in .env")
    if not SENDER_EMAIL:
        raise ValueError("SENDER_EMAIL is not set in .env")

    sendable = [c for c in contacts if c.email]
    if not sendable:
        warn("No contacts with verified emails to send.")
        return 0, 0

    info(f"Sending {len(sendable)} outreach emails...")
    sent = 0
    failed = 0

    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json",
    }

    for contact in sendable:
        html_content, text_content = _render_template(contact)
        company_name = contact.company_name or contact.company_domain
        payload = {
            "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
            "to": [{"email": contact.email, "name": contact.full_name}],
            "subject": f"Quick idea for {company_name}",
            "htmlContent": html_content,
            "textContent": text_content,
            "tags": ["outreach-pipeline"],
        }
        request_headers = {
            **headers,
            "Idempotency-Key": f"outreach-{contact.person_id}",
        }

        response = request_with_retry(
            "POST",
            f"{BREVO_BASE_URL}/smtp/email",
            headers=request_headers,
            json=payload,
        )

        if response.status_code == 201:
            sent += 1
            success(f"Sent to {contact.full_name} <{contact.email}>")
        else:
            failed += 1
            error(
                f"Failed to send to {contact.full_name} ({response.status_code}): "
                f"{response.text}"
            )

    return sent, failed
