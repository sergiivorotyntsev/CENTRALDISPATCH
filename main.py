#!/usr/bin/env python3
"""
Vehicle Transport Automation - Email to ClickUp Pipeline

CLI Commands:
    extract <pdf>      - Extract data from a single PDF file
    once               - Run single pass: fetch and process unseen emails
    daemon             - Run continuously, polling for new emails
    validate           - Validate all credentials (email, ClickUp, CD)
    idempotency        - Manage idempotency database

Usage:
    python main.py extract invoice.pdf
    python main.py once --dry-run
    python main.py daemon --interval 60
    python main.py validate
"""
import argparse
import json
import sys
import os

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def cmd_extract(args):
    """Extract data from a PDF file."""
    from extractors import extract_from_pdf
    from core.logging_config import setup_logging

    setup_logging(level="INFO", format_type="text")

    pdf_path = args.pdf
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        return 1

    print(f"Extracting from: {pdf_path}")
    print("-" * 50)

    invoice = extract_from_pdf(pdf_path)

    if invoice:
        print(f"Source: {invoice.source.value}")
        print(f"Buyer ID: {invoice.buyer_id}")
        print(f"Buyer Name: {invoice.buyer_name}")
        print(f"Sale Date: {invoice.sale_date}")
        print(f"Reference ID: {invoice.reference_id}")
        print(f"Total Amount: ${invoice.total_amount:,.2f}" if invoice.total_amount else "Total Amount: N/A")

        if invoice.pickup_address:
            addr = invoice.pickup_address
            print(f"\nPickup Address:")
            if addr.name:
                print(f"  Name: {addr.name}")
            if addr.street:
                print(f"  Street: {addr.street}")
            print(f"  City: {addr.city}, {addr.state} {addr.postal_code}")

        print(f"\nVehicles ({len(invoice.vehicles)}):")
        for i, v in enumerate(invoice.vehicles, 1):
            print(f"  {i}. {v.year} {v.make} {v.model}")
            print(f"     VIN: {v.vin}")
            if v.lot_number:
                print(f"     Lot #: {v.lot_number}")
            if v.color:
                print(f"     Color: {v.color}")
            if v.mileage:
                print(f"     Mileage: {v.mileage:,}")

        if args.json:
            print("\n--- JSON Output ---")
            output = {
                "source": invoice.source.value,
                "buyer_id": invoice.buyer_id,
                "buyer_name": invoice.buyer_name,
                "reference_id": invoice.reference_id,
                "vehicles": [
                    {
                        "vin": v.vin,
                        "year": v.year,
                        "make": v.make,
                        "model": v.model,
                        "lot_number": v.lot_number,
                        "color": v.color,
                        "mileage": v.mileage,
                    }
                    for v in invoice.vehicles
                ],
            }
            print(json.dumps(output, indent=2))

        return 0
    else:
        print("ERROR: Could not extract data from PDF")
        print("The document format may not be recognized (Copart/IAA/Manheim)")
        return 1


def cmd_once(args):
    """Run a single pass of email processing."""
    from core.config import load_config_from_env
    from core.logging_config import setup_logging
    from services.orchestrator import Orchestrator

    config = load_config_from_env()
    config.dry_run = args.dry_run

    setup_logging(level=config.log_level, format_type=config.log_format)

    # Validate config
    try:
        config.validate(require_email=True, require_clickup=not args.dry_run)
    except Exception as e:
        print(f"Configuration error: {e}")
        return 1

    print("Running single pass...")
    if args.dry_run:
        print("(DRY RUN - no tasks will be created)")

    orchestrator = Orchestrator(config)
    results = orchestrator.run_once()

    # Print summary
    print(f"\nProcessed {len(results)} emails:")
    for result in results:
        status = "ERROR" if result.error else "OK"
        print(f"  [{status}] {result.subject}")
        if result.gate_pass:
            print(f"       Gate Pass: {result.gate_pass}")
        for att in result.attachment_results:
            att_status = "SKIP" if att.skipped_duplicate else ("OK" if att.success else "FAIL")
            print(f"       [{att_status}] {att.attachment_name}")
            if att.clickup_task_url:
                print(f"              Task: {att.clickup_task_url}")
            if att.error:
                print(f"              Error: {att.error}")

    return 0


def cmd_daemon(args):
    """Run in daemon mode."""
    from core.config import load_config_from_env
    from core.logging_config import setup_logging
    from services.orchestrator import run_daemon

    config = load_config_from_env()

    setup_logging(level=config.log_level, format_type=config.log_format)

    # Validate config
    try:
        config.validate()
    except Exception as e:
        print(f"Configuration error: {e}")
        return 1

    print(f"Starting daemon mode (interval: {args.interval or config.email.check_interval}s)")
    print("Press Ctrl+C to stop")

    run_daemon(config, interval=args.interval)
    return 0


def cmd_validate(args):
    """Validate all credentials."""
    from core.config import load_config_from_env
    from ingest.email_reader import create_email_reader
    from services.clickup import ClickUpClient

    print("Validating credentials...")
    print("-" * 50)

    config = load_config_from_env()
    all_ok = True

    # Validate Email
    print("\n[Email]")
    if config.email.address:
        print(f"  Provider: {config.email.provider}")
        print(f"  Address: {config.email.address}")
        if config.email.provider == "imap":
            print(f"  Server: {config.email.imap_server}")

        try:
            reader = create_email_reader(config.email)
            success, message = reader.validate_connection()
            if success:
                print(f"  Status: OK - {message}")
            else:
                print(f"  Status: FAILED - {message}")
                all_ok = False
        except Exception as e:
            print(f"  Status: ERROR - {e}")
            all_ok = False
    else:
        print("  Status: NOT CONFIGURED")
        if not args.skip_email:
            all_ok = False

    # Validate ClickUp
    print("\n[ClickUp]")
    if config.clickup.token and config.clickup.list_id:
        print(f"  List ID: {config.clickup.list_id}")

        try:
            client = ClickUpClient(
                token=config.clickup.token,
                list_id=config.clickup.list_id,
            )
            if client.validate_credentials():
                print("  Status: OK")
            else:
                print("  Status: FAILED - Invalid credentials")
                all_ok = False
        except Exception as e:
            print(f"  Status: ERROR - {e}")
            all_ok = False
    else:
        print("  Status: NOT CONFIGURED")
        if not args.skip_clickup:
            all_ok = False

    # Validate Central Dispatch (optional)
    print("\n[Central Dispatch]")
    if config.central_dispatch.enabled:
        print(f"  Marketplace ID: {config.central_dispatch.marketplace_id}")

        try:
            from services.central_dispatch import CentralDispatchClient
            cd_client = CentralDispatchClient(
                client_id=config.central_dispatch.client_id,
                client_secret=config.central_dispatch.client_secret,
                marketplace_id=config.central_dispatch.marketplace_id,
            )
            if cd_client.validate_credentials():
                print("  Status: OK")
            else:
                print("  Status: FAILED - Invalid credentials")
                # CD is optional, don't fail
        except Exception as e:
            print(f"  Status: ERROR - {e}")
    else:
        print("  Status: DISABLED (optional)")

    print("-" * 50)
    if all_ok:
        print("All required credentials validated successfully!")
        return 0
    else:
        print("Some credentials failed validation. Check configuration.")
        return 1


def cmd_idempotency(args):
    """Manage idempotency database."""
    from core.config import load_config_from_env
    from services.idempotency import IdempotencyStore

    config = load_config_from_env()
    store = IdempotencyStore(db_path=config.storage.idempotency_db_path)

    if args.action == "stats":
        # Show stats
        with store._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM processed_items")
            total = cursor.fetchone()[0]

            cursor = conn.execute("""
                SELECT source_type, COUNT(*)
                FROM processed_items
                GROUP BY source_type
            """)
            by_source = cursor.fetchall()

            cursor = conn.execute("""
                SELECT date(processed_at), COUNT(*)
                FROM processed_items
                GROUP BY date(processed_at)
                ORDER BY date(processed_at) DESC
                LIMIT 7
            """)
            by_day = cursor.fetchall()

        print(f"Idempotency Database: {config.storage.idempotency_db_path}")
        print(f"Total records: {total}")
        print("\nBy source:")
        for source, count in by_source:
            print(f"  {source or 'UNKNOWN'}: {count}")
        print("\nLast 7 days:")
        for day, count in by_day:
            print(f"  {day}: {count}")

    elif args.action == "purge":
        if not args.days:
            print("Error: --days required for purge")
            return 1

        with store._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM processed_items WHERE processed_at < datetime('now', ?)",
                (f"-{args.days} days",)
            )
            deleted = cursor.rowcount
            conn.commit()

        print(f"Purged {deleted} records older than {args.days} days")

    elif args.action == "list":
        limit = args.limit or 20
        with store._get_connection() as conn:
            cursor = conn.execute("""
                SELECT idempotency_key, source_type, result_id, processed_at
                FROM processed_items
                ORDER BY processed_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()

        print(f"Last {limit} processed items:")
        for row in rows:
            print(f"  {row['processed_at']} | {row['source_type']} | {row['result_id']}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Vehicle Transport Automation - Email to ClickUp Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py extract invoice.pdf --json
    python main.py once --dry-run
    python main.py daemon --interval 120
    python main.py validate
    python main.py idempotency stats
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # extract command
    extract_parser = subparsers.add_parser("extract", help="Extract data from a PDF file")
    extract_parser.add_argument("pdf", help="Path to PDF file")
    extract_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # once command
    once_parser = subparsers.add_parser("once", help="Run single pass of email processing")
    once_parser.add_argument("--dry-run", action="store_true", help="Don't create ClickUp tasks")

    # daemon command
    daemon_parser = subparsers.add_parser("daemon", help="Run continuously")
    daemon_parser.add_argument("--interval", type=int, help="Check interval in seconds")

    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate credentials")
    validate_parser.add_argument("--skip-email", action="store_true", help="Skip email validation")
    validate_parser.add_argument("--skip-clickup", action="store_true", help="Skip ClickUp validation")

    # idempotency command
    idem_parser = subparsers.add_parser("idempotency", help="Manage idempotency database")
    idem_parser.add_argument("action", choices=["stats", "purge", "list"], help="Action to perform")
    idem_parser.add_argument("--days", type=int, help="Days for purge")
    idem_parser.add_argument("--limit", type=int, help="Limit for list")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "extract": cmd_extract,
        "once": cmd_once,
        "daemon": cmd_daemon,
        "validate": cmd_validate,
        "idempotency": cmd_idempotency,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
