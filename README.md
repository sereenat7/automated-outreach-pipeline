# Automated Outreach Pipeline

A fully automated cold-outreach CLI. Enter one company domain — the pipeline finds lookalike companies, surfaces decision-makers, resolves verified work emails, and sends personalized outreach via Brevo.

## Architecture

```
company.domain (human input)
    → Ocean.io      — find lookalike companies
    → Prospeo       — find C-suite / VP contacts + verified emails
    → Safety check  — review summary, confirm before send
    → Brevo         — send personalized outreach emails
```

## Prerequisites

- Python 3.10+
- API accounts: [Ocean.io](https://ocean.io), [Prospeo](https://app.prospeo.io/api), [Brevo](https://app.brevo.com)
- A verified sender domain on Brevo (e.g. `hello@yourdomain.com`)

## Setup

```bash
# Clone and enter the project
cd automated-outreach-pipeline

# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your keys
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `OCEAN_API_KEY` | Ocean.io API token |
| `PROSPEO_API_KEY` | Prospeo API key |
| `BREVO_API_KEY` | Brevo API key |
| `SENDER_EMAIL` | Verified sender email (e.g. `hello@sereena.live`) |
| `SENDER_NAME` | Display name for outgoing emails |

## Usage

```bash
# Full run (25 lookalike companies by default)
python main.py stripe.com

# Smaller run to save API credits
python main.py stripe.com --limit 10

# Dry run — runs all stages except sending emails
python main.py stripe.com --dry-run

# Skip confirmation prompt (use with caution)
python main.py stripe.com --yes
```

### Example output

1. Finds lookalike companies via Ocean.io
2. Finds decision-makers via Prospeo
3. Resolves verified emails via Prospeo bulk enrich
4. Shows a summary table of contacts
5. Prompts: `Ready to send N email(s). Proceed? [y/N]:`
6. Sends personalized emails via Brevo

## Safety checkpoint

Before any email is sent, the pipeline prints a summary table and waits for confirmation. The default is **No** — pressing Enter aborts without sending.

Use `--dry-run` to test the full pipeline without consuming Brevo send quota.

## Project structure

```
├── main.py              # CLI entry point and orchestration
├── config.py            # Environment and constants
├── models.py            # Company and Contact dataclasses
├── stages/
│   ├── ocean.py         # Lookalike company search
│   ├── prospeo.py       # Contact search + email enrichment
│   └── brevo.py         # Outreach email sending
├── templates/
│   └── email.html       # Email template with placeholders
└── utils/
    ├── http.py          # HTTP client with retry/backoff
    └── logging.py       # Console output helpers
```

## API credit notes

| Service | Approximate cost per run (25 companies) |
|---------|------------------------------------------|
| Ocean.io | ~5 credits (0.2 per company) |
| Prospeo | ~1 search credit + up to 25 enrich credits |
| Brevo | 1 send per contact (free tier: 300/day) |

Start with `--limit 5 --dry-run` to verify everything works before a full run.

## Error handling

- Rate limits (429): automatic retry with exponential backoff
- Missing contacts or emails: logged and skipped, pipeline continues
- Insufficient Ocean credits (402): stage stops with a clear error
- Partial Brevo failures: logged per contact, final success/fail count reported

## Author

Sereena Thomas — SDE Intern assignment @ Vocallabs/Subspace
