import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

OCEAN_API_KEY = os.environ.get("OCEAN_API_KEY", "")
PROSPEO_API_KEY = os.environ.get("PROSPEO_API_KEY", "")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_NAME = os.environ.get("SENDER_NAME", "")

COMPANY_LIMIT = 25
MAX_CONTACTS_PER_COMPANY = 1
OCEAN_PAGE_SIZE = 25
PROSPEO_DOMAIN_BATCH_SIZE = 500
PROSPEO_ENRICH_BATCH_SIZE = 50

OCEAN_BASE_URL = "https://api.ocean.io"
PROSPEO_BASE_URL = "https://api.prospeo.io"
BREVO_BASE_URL = "https://api.brevo.com/v3"

MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 1.0
