#!/usr/bin/env python3
import argparse
import sys

from rich.console import Console
from rich.table import Table

from config import COMPANY_LIMIT
from pipeline_runner import run_pipeline, send_to_contacts, validate_config
from stages.ocean import normalize_domain
from utils.logging import error, info, success, warn

console = Console()


def print_summary(contacts: list[dict]) -> None:
    table = Table(title="Outreach Summary", show_header=True, header_style="bold")
    table.add_column("Company", style="cyan")
    table.add_column("Contact", style="green")
    table.add_column("Title")
    table.add_column("LinkedIn", style="blue")
    table.add_column("Email")

    for contact in contacts:
        table.add_row(
            contact.get("company_name") or contact.get("company_domain", ""),
            contact.get("full_name", ""),
            contact.get("job_title") or "—",
            contact.get("linkedin_url") or "—",
            contact.get("email") or "—",
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

    missing = validate_config()
    if missing:
        error(f"Missing required environment variables: {', '.join(missing)}")
        error("Copy .env.example to .env and fill in your API keys.")
        return 1

    seed = normalize_domain(args.domain)
    if not seed:
        error("Invalid domain provided.")
        return 1

    console.print(f"\n[bold]Automated Outreach Pipeline[/bold]")
    console.print(f"Seed domain: [cyan]{seed}[/cyan]\n")

    def on_log(message: str, level: str) -> None:
        if level == "error":
            error(message)
        elif level == "success":
            success(message)
        elif level == "warn":
            warn(message)
        elif level == "stage":
            info(message)
        else:
            info(message)

    result = run_pipeline(
        args.domain,
        limit=args.limit,
        dry_run=args.dry_run,
        send=args.yes,
        on_log=on_log,
    )

    if not result.get("ok") and not result.get("contacts"):
        if result.get("error"):
            error(result["error"])
        return 1

    contacts = result.get("contacts", [])
    if contacts:
        print_summary(contacts)

    if args.dry_run:
        info("Dry run complete — no emails sent.")
        return 0

    if not contacts:
        return 1

    if args.yes:
        success(
            f"Pipeline complete: {result.get('sent', 0)} sent, {result.get('failed', 0)} failed."
        )
        return 0 if result.get("ok") else 1

    if not confirm_send(len(contacts), False):
        info("Aborted. No emails sent.")
        return 0

    send_result = send_to_contacts(contacts, on_log=on_log)
    success(f"Pipeline complete: {send_result.get('sent', 0)} sent, {send_result.get('failed', 0)} failed.")
    return 0 if send_result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
