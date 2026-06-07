import re
from urllib.parse import urlparse

from config import OCEAN_API_KEY, OCEAN_BASE_URL, OCEAN_PAGE_SIZE
from models import Company
from utils.http import request_with_retry
from utils.logging import error, info, warn


def normalize_domain(raw: str) -> str:
    value = raw.strip().lower()
    if "://" in value:
        value = urlparse(value).netloc or urlparse(f"https://{value}").path
    value = value.removeprefix("www.")
    value = value.split("/")[0]
    value = re.sub(r"[^a-z0-9.\-]", "", value)
    return value


def find_lookalike_companies(seed_domain: str, limit: int) -> list[Company]:
    if not OCEAN_API_KEY:
        raise ValueError("OCEAN_API_KEY is not set in .env")

    domain = normalize_domain(seed_domain)
    info(f"Finding lookalike companies for {domain}...")

    headers = {
        "X-Api-Token": OCEAN_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "size": min(limit, OCEAN_PAGE_SIZE),
        "companiesFilters": {
            "lookalikeDomains": [domain],
            "excludeDomains": [domain],
        },
    }

    response = request_with_retry(
        "POST",
        f"{OCEAN_BASE_URL}/v3/search/companies",
        headers=headers,
        json=payload,
    )

    if response.status_code == 402:
        error("Ocean.io: insufficient credits.")
        return []

    if response.status_code != 200:
        error(f"Ocean.io request failed ({response.status_code}): {response.text}")
        return []

    data = response.json()
    seen: set[str] = set()
    companies: list[Company] = []

    for item in data.get("companies", []):
        company_data = item.get("company", {})
        company_domain = normalize_domain(company_data.get("domain", ""))
        if not company_domain or company_domain in seen or company_domain == domain:
            continue
        seen.add(company_domain)
        companies.append(
            Company(
                domain=company_domain,
                name=company_data.get("name") or company_domain,
            )
        )
        if len(companies) >= limit:
            break

    if not companies:
        warn("No lookalike companies found. Try a different seed domain.")
    else:
        info(f"Found {len(companies)} lookalike companies.")

    return companies
