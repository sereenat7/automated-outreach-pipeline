from dataclasses import asdict
from typing import Callable

from config import COMPANY_LIMIT, BREVO_API_KEY, OCEAN_API_KEY, PROSPEO_API_KEY
from models import Contact
from stages.brevo import send_outreach_emails
from stages.ocean import find_lookalike_companies, normalize_domain
from stages.prospeo import enrich_contacts, search_decision_makers

LogCallback = Callable[[str, str], None]


def validate_config() -> list[str]:
    missing = []
    if not OCEAN_API_KEY:
        missing.append("OCEAN_API_KEY")
    if not PROSPEO_API_KEY:
        missing.append("PROSPEO_API_KEY")
    if not BREVO_API_KEY:
        missing.append("BREVO_API_KEY")
    return missing


def contact_to_dict(contact: Contact) -> dict:
    return {
        "person_id": contact.person_id,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "full_name": contact.full_name,
        "email": contact.email,
        "linkedin_url": contact.linkedin_url,
        "job_title": contact.job_title,
        "company_domain": contact.company_domain,
        "company_name": contact.company_name,
    }


def contact_from_dict(data: dict) -> Contact:
    return Contact(
        person_id=data["person_id"],
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        email=data.get("email"),
        linkedin_url=data.get("linkedin_url", ""),
        job_title=data.get("job_title", ""),
        company_domain=data.get("company_domain", ""),
        company_name=data.get("company_name", ""),
    )


def run_pipeline(
    domain: str,
    *,
    limit: int = COMPANY_LIMIT,
    dry_run: bool = False,
    send: bool = False,
    on_log: LogCallback | None = None,
) -> dict:
    def log(message: str, level: str = "info") -> None:
        if on_log:
            on_log(message, level)

    missing = validate_config()
    if missing:
        return {
            "ok": False,
            "error": f"Missing environment variables: {', '.join(missing)}",
        }

    seed = normalize_domain(domain)
    if not seed:
        return {"ok": False, "error": "Invalid domain provided."}

    log(f"Starting pipeline for {seed}", "info")

    log("Stage 1: Finding lookalike companies via Ocean.io...", "stage")
    companies = find_lookalike_companies(seed, limit)
    if not companies:
        return {"ok": False, "error": "No lookalike companies found.", "seed": seed}

    log(f"Found {len(companies)} lookalike companies.", "success")

    log("Stage 2: Finding decision-makers via Prospeo...", "stage")
    contacts = search_decision_makers(companies)
    if not contacts:
        return {"ok": False, "error": "No decision-makers found.", "seed": seed}

    log(f"Found {len(contacts)} decision-makers.", "success")

    log("Stage 3: Resolving verified emails via Prospeo...", "stage")
    enriched = enrich_contacts(contacts)
    if not enriched:
        return {
            "ok": False,
            "error": "No verified emails resolved.",
            "seed": seed,
        }

    log(f"Resolved {len(enriched)} verified emails.", "success")
    contact_dicts = [contact_to_dict(c) for c in enriched]

    if dry_run:
        log("Dry run complete — no emails sent.", "success")
        return {
            "ok": True,
            "seed": seed,
            "contacts": contact_dicts,
            "dry_run": True,
            "sent": 0,
            "failed": 0,
        }

    if not send:
        log("Pipeline ready — awaiting send confirmation.", "warn")
        return {
            "ok": True,
            "seed": seed,
            "contacts": contact_dicts,
            "awaiting_confirmation": True,
            "sent": 0,
            "failed": 0,
        }

    log("Stage 4: Sending outreach emails via Brevo...", "stage")
    sent, failed = send_outreach_emails(enriched)
    log(f"Pipeline complete: {sent} sent, {failed} failed.", "success" if failed == 0 else "warn")

    return {
        "ok": failed == 0,
        "seed": seed,
        "contacts": contact_dicts,
        "sent": sent,
        "failed": failed,
    }


def send_to_contacts(contact_dicts: list[dict], on_log: LogCallback | None = None) -> dict:
    def log(message: str, level: str = "info") -> None:
        if on_log:
            on_log(message, level)

    contacts = [contact_from_dict(c) for c in contact_dicts if c.get("email")]
    if not contacts:
        return {"ok": False, "error": "No contacts with emails to send."}

    log("Sending outreach emails via Brevo...", "stage")
    sent, failed = send_outreach_emails(contacts)
    log(f"Done: {sent} sent, {failed} failed.", "success" if failed == 0 else "warn")
    return {"ok": failed == 0, "sent": sent, "failed": failed}
