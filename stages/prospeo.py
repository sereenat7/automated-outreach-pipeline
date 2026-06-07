import time

from config import (
    PROSPEO_API_KEY,
    PROSPEO_BASE_URL,
    PROSPEO_DOMAIN_BATCH_SIZE,
    PROSPEO_ENRICH_BATCH_SIZE,
)
from models import Company, Contact
from utils.http import request_with_retry
from utils.logging import error, info, warn


def _headers() -> dict[str, str]:
    return {
        "X-KEY": PROSPEO_API_KEY,
        "Content-Type": "application/json",
    }


def _parse_contact(result: dict) -> Contact | None:
    person = result.get("person", {})
    company = result.get("company", {})
    person_id = person.get("person_id")
    if not person_id:
        return None

    return Contact(
        person_id=person_id,
        first_name=person.get("first_name", ""),
        last_name=person.get("last_name", ""),
        email=None,
        linkedin_url=person.get("linkedin_url", ""),
        job_title=person.get("current_job_title", ""),
        company_domain=company.get("domain", ""),
        company_name=company.get("name", ""),
    )


def search_decision_makers(companies: list[Company]) -> list[Contact]:
    if not PROSPEO_API_KEY:
        raise ValueError("PROSPEO_API_KEY is not set in .env")
    if not companies:
        return []

    domains = [c.domain for c in companies]
    all_contacts: list[Contact] = []
    seen_person_ids: set[str] = set()

    info("Finding decision-makers...")

    for i in range(0, len(domains), PROSPEO_DOMAIN_BATCH_SIZE):
        batch = domains[i : i + PROSPEO_DOMAIN_BATCH_SIZE]
        page = 1

        while True:
            payload = {
                "page": page,
                "filters": {
                    "company": {"websites": {"include": batch}},
                    "person_seniority": {
                        "include": ["C-Suite", "Vice President", "Founder/Owner"]
                    },
                    "max_person_per_company": 1,
                },
            }

            response = request_with_retry(
                "POST",
                f"{PROSPEO_BASE_URL}/search-person",
                headers=_headers(),
                json=payload,
            )

            if response.status_code != 200:
                error(f"Prospeo search failed ({response.status_code}): {response.text}")
                break

            data = response.json()
            if data.get("error"):
                error(f"Prospeo search error: {data}")
                break

            for result in data.get("results", []):
                contact = _parse_contact(result)
                if contact and contact.person_id not in seen_person_ids:
                    seen_person_ids.add(contact.person_id)
                    all_contacts.append(contact)

            pagination = data.get("pagination", {})
            total_page = pagination.get("total_page", 1)
            if page >= total_page:
                break
            page += 1

    if not all_contacts:
        warn("No decision-makers found for the given companies.")
    else:
        info(f"Found {len(all_contacts)} decision-makers.")

    return all_contacts


def enrich_contacts(contacts: list[Contact]) -> list[Contact]:
    if not contacts:
        return []

    info("Resolving verified work emails...")
    enriched: list[Contact] = []
    time.sleep(3)

    for i in range(0, len(contacts), PROSPEO_ENRICH_BATCH_SIZE):
        if i > 0:
            time.sleep(2)
        batch = contacts[i : i + PROSPEO_ENRICH_BATCH_SIZE]
        payload = {
            "only_verified_email": True,
            "enrich_mobile": False,
            "data": [
                {"identifier": str(idx), "person_id": c.person_id}
                for idx, c in enumerate(batch, start=1)
            ],
        }

        response = request_with_retry(
            "POST",
            f"{PROSPEO_BASE_URL}/bulk-enrich-person",
            headers=_headers(),
            json=payload,
        )

        if response.status_code != 200:
            error(f"Prospeo enrich failed ({response.status_code}): {response.text}")
            continue

        data = response.json()
        if data.get("error"):
            error(f"Prospeo enrich error: {data}")
            continue

        matched_by_id = {
            item.get("identifier"): item for item in data.get("matched", [])
        }

        for idx, contact in enumerate(batch, start=1):
            match = matched_by_id.get(str(idx))
            if not match:
                warn(f"No email found for {contact.full_name} at {contact.company_name}")
                continue

            person = match.get("person", {})
            email_data = person.get("email", {})
            if (
                email_data.get("status") == "VERIFIED"
                and email_data.get("revealed")
                and email_data.get("email")
            ):
                contact.email = email_data["email"]
                enriched.append(contact)
            else:
                warn(f"Unverified or missing email for {contact.full_name}")

        not_matched = data.get("not_matched", [])
        if not_matched:
            warn(f"Prospeo could not match {len(not_matched)} contact(s) in this batch.")

    info(f"Resolved {len(enriched)} verified emails.")
    return enriched
