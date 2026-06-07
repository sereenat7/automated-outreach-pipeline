#!/usr/bin/env python3
import argparse
import sys

from rich.console import Console
from rich.table import Table

from config import COMPANY_LIMIT, OCEAN_API_KEY, PROSPEO_API_KEY, BREVO_API_KEY
from stages.brevo import send_outreach_emails
from stages.ocean import find_lookalike_companies, normalize_domain
from stages.prospeo import enrich_contacts, search_decision_makers
from utils.logging import error, info, success, warn

console = Console()


def validate_config() -> bool:
    missing = []
    if not OCEAN_API_KEY:
        missing.append("OCEAN_API_KEY")
    if not PROSPEO_API_KEY:
        missing.append("PROSPEO_API_KEY")
    if not BREVO_API_KEY:
        missing.append("BREVO_API_KEY")
    if missing:
        error(f"Missing required environment variables: {', '.join(missing)}")
        error("Copy .env.example to .env and fill in your API keys.")
        return False
    return True


def print_summary(contacts: list) -> None:
    table = Table(title="Outreach Summary", show_header=True, header_style="bold")
    table.add_column("Company", style="cyan")
    table.add_column("Contact", style="green")
    table.add_column("Title")
    table.add_column("Email")

    for contact in contacts:
        table.add_row(
            contact.company_name or contact.company_domain,
            contact.full_name,
            contact.job_title or "—",
            contact.email or "—",
        )

    console.print(table)


def confirm_send(count: int, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    prompt = f"\nReady to send {count} email(s). Proceed? [y/N]: "
    answer = input(prompt).strip().lower()
    return answer in ("y", "yes")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automated cold-outreach pipeline: one domain in, emails out."
    )
    parser.add_argument("domain", help="Seed company domain (e.g. stripe.com)")
    parser.add_argument(
        "--limit",
        type=int,
        default=COMPANY_LIMIT,
        help=f"Max lookalike companies to process (default: {COMPANY_LIMIT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without sending emails",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt and send immediately",
    )
    args = parser.parse_args()

    if not validate_config():
        return 1

    seed = normalize_domain(args.domain)
    if not seed:
        error("Invalid domain provided.")
        return 1

    console.print(f"\n[bold]Automated Outreach Pipeline[/bold]")
    console.print(f"Seed domain: [cyan]{seed}[/cyan]\n")

    companies = find_lookalike_companies(seed, args.limit)
    if not companies:
        return 1

    contacts = search_decision_makers(companies)
    if not contacts:
        return 1

    enriched = enrich_contacts(contacts)
    if not enriched:
        warn("No verified emails resolved. Pipeline complete without sending.")
        return 0

    print_summary(enriched)

    if args.dry_run:
        info("Dry run complete — no emails sent.")
        return 0

    if not confirm_send(len(enriched), args.yes):
        info("Aborted. No emails sent.")
        return 0

    sent, failed = send_outreach_emails(enriched)
    success(f"Pipeline complete: {sent} sent, {failed} failed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
