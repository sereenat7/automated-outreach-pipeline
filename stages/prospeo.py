import time

import requests

from config import (
    PROSPEO_API_KEY,
    PROSPEO_BASE_URL,
    PROSPEO_DOMAIN_BATCH_SIZE,
    PROSPEO_ENRICH_BATCH_SIZE,
)
from models import Company, Contact
from utils.http import request_with_retry
from utils.logging import error, info, warn

# Free plan allows 1 search request/second — wait between Prospeo calls.
PROSPEO_MIN_INTERVAL = 1.2
_last_request_at = 0.0
_last_response: requests.Response | None = None


def _headers() -> dict[str, str]:
    return {
        "X-KEY": PROSPEO_API_KEY,
        "Content-Type": "application/json",
    }


def _wait_for_rate_limit(response: requests.Response | None = None) -> None:
    global _last_request_at

    elapsed = time.monotonic() - _last_request_at
    if elapsed < PROSPEO_MIN_INTERVAL:
        time.sleep(PROSPEO_MIN_INTERVAL - elapsed)

    if response is not None:
        second_left = response.headers.get("x-second-request-left")
        reset_seconds = response.headers.get("x-second-reset-seconds")
        if second_left is not None and int(second_left) <= 0:
            wait = float(reset_seconds or 1) + 0.5
            warn(f"Prospeo rate limit: waiting {wait:.1f}s...")
            time.sleep(wait)


def _prospeo_post(url: str, payload: dict) -> requests.Response:
    global _last_request_at, _last_response

    _wait_for_rate_limit(_last_response)
    response = request_with_retry("POST", url, headers=_headers(), json=payload)
    _last_request_at = time.monotonic()
    _last_response = response
    return response


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


def _extract_verified_email(person: dict) -> str | None:
    email_data = person.get("email", {})
    if (
        email_data.get("status") == "VERIFIED"
        and email_data.get("revealed")
        and email_data.get("email")
    ):
        return email_data["email"]
    return None


def _enrich_payload_item(contact: Contact, identifier: str) -> dict:
    item: dict[str, str] = {"identifier": identifier, "person_id": contact.person_id}
    if contact.linkedin_url:
        item["linkedin_url"] = contact.linkedin_url
    if contact.company_domain:
        item["company_website"] = contact.company_domain
    if contact.company_name:
        item["company_name"] = contact.company_name
    if contact.first_name:
        item["first_name"] = contact.first_name
    if contact.last_name:
        item["last_name"] = contact.last_name
    return item


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

            response = _prospeo_post(f"{PROSPEO_BASE_URL}/search-person", payload)

            if response.status_code == 401:
                error("Prospeo: invalid API key. Check PROSPEO_API_KEY in .env")
                return []

            if response.status_code != 200:
                error(f"Prospeo search failed ({response.status_code}): {response.text}")
                break

            data = response.json()
            if data.get("error"):
                error_code = data.get("error_code", "unknown")
                error(f"Prospeo search error ({error_code}): {data}")
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


def _enrich_batch_bulk(batch: list[Contact]) -> list[Contact]:
    global _last_request_at, _last_response

    payload = {
        "only_verified_email": True,
        "enrich_mobile": False,
        "data": [
            _enrich_payload_item(contact, str(idx))
            for idx, contact in enumerate(batch, start=1)
        ],
    }

    # Try bulk once; on rate limit, fall back to single enrich immediately.
    _wait_for_rate_limit(_last_response)
    response = requests.post(
        f"{PROSPEO_BASE_URL}/bulk-enrich-person",
        headers=_headers(),
        json=payload,
        timeout=60,
    )
    _last_request_at = time.monotonic()
    _last_response = response

    if response.status_code == 429:
        return []

    if response.status_code != 200:
        error(f"Prospeo bulk enrich failed ({response.status_code}): {response.text}")
        return []

    data = response.json()
    if data.get("error"):
        error_code = data.get("error_code", "unknown")
        error(f"Prospeo bulk enrich error ({error_code}): {data}")
        return []

    enriched: list[Contact] = []
    matched_by_id = {item.get("identifier"): item for item in data.get("matched", [])}

    for idx, contact in enumerate(batch, start=1):
        match = matched_by_id.get(str(idx))
        if not match:
            continue
        email = _extract_verified_email(match.get("person", {}))
        if email:
            contact.email = email
            enriched.append(contact)
        else:
            warn(f"Unverified or missing email for {contact.full_name}")

    not_matched = data.get("not_matched", [])
    if not_matched:
        warn(f"Prospeo could not match {len(not_matched)} contact(s) in bulk batch.")

    return enriched


def _enrich_single(contact: Contact) -> Contact | None:
    data: dict[str, str] = {"person_id": contact.person_id}
    if contact.linkedin_url:
        data["linkedin_url"] = contact.linkedin_url
    if contact.company_domain:
        data["company_website"] = contact.company_domain
    if contact.company_name:
        data["company_name"] = contact.company_name
    if contact.first_name:
        data["first_name"] = contact.first_name
    if contact.last_name:
        data["last_name"] = contact.last_name

    payload = {"only_verified_email": True, "data": data}
    response = _prospeo_post(f"{PROSPEO_BASE_URL}/enrich-person", payload)

    if response.status_code == 429:
        warn(f"Rate limited while enriching {contact.full_name}. Skipping for now.")
        return None

    if response.status_code != 200:
        error(f"Prospeo enrich failed for {contact.full_name} ({response.status_code})")
        return None

    data = response.json()
    if data.get("error"):
        error_code = data.get("error_code", "unknown")
        if error_code != "NO_MATCH":
            warn(f"Could not enrich {contact.full_name}: {error_code}")
        return None

    email = _extract_verified_email(data.get("person", {}))
    if email:
        contact.email = email
        return contact

    warn(f"Unverified or missing email for {contact.full_name}")
    return None


def enrich_contacts(contacts: list[Contact]) -> list[Contact]:
    if not contacts:
        return []

    info("Resolving verified work emails...")
    _wait_for_rate_limit(_last_response)

    enriched: list[Contact] = []
    pending = list(contacts)

    for i in range(0, len(pending), PROSPEO_ENRICH_BATCH_SIZE):
        batch = pending[i : i + PROSPEO_ENRICH_BATCH_SIZE]
        batch_results = _enrich_batch_bulk(batch)

        if batch_results:
            enriched.extend(batch_results)
            continue

        warn("Bulk enrich unavailable or rate limited — falling back to single enrich.")
        for contact in batch:
            result = _enrich_single(contact)
            if result:
                enriched.append(result)

    info(f"Resolved {len(enriched)} verified emails.")
    return enriched
