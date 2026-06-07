import time
from typing import Any

import requests

from config import MAX_RETRIES, RETRY_BACKOFF_BASE
from utils.logging import error, warn


def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, Any] | None = None,
    retry_statuses: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> requests.Response:
    last_response: requests.Response | None = None

    for attempt in range(MAX_RETRIES):
        response = requests.request(method, url, headers=headers, json=json, timeout=60)
        last_response = response

        if response.status_code not in retry_statuses:
            return response

        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            wait = float(retry_after)
        elif response.status_code == 429:
            wait = max(RETRY_BACKOFF_BASE * (2**attempt), 5.0)
        else:
            wait = RETRY_BACKOFF_BASE * (2**attempt)

        warn(f"Request failed with {response.status_code}. Retrying in {wait:.0f}s...")
        time.sleep(wait)

    if last_response is not None:
        return last_response
    raise RuntimeError(f"Request failed after {MAX_RETRIES} retries: {url}")
