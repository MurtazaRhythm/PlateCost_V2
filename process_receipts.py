"""Reads multi-photo receipts with Gemini and saves them to Supabase.

Each subfolder of "Receipt demos" is one receipt; its images are the receipt's
sections in filename order.

    python process_receipts.py                    # all folders
    python process_receipts.py --folder ROne      # one folder
    python process_receipts.py --dry-run          # print extracted JSON only

Errors, warnings and timings are reported to Sentry. With no SENTRY_DSN they go
only to a local Spotlight sidecar (http://localhost:8969); set SENTRY_SPOTLIGHT=0
to turn that off.
"""

import argparse
import os
import sys
from pathlib import Path

import sentry_sdk
from dotenv import load_dotenv
from google import genai
from sentry_sdk import logger as sentry_logger

from receipts.extract import extract_receipt, list_images
from receipts.models import check_totals, reconcile_purchase_date

ROOT = Path(__file__).resolve().parent
DEFAULT_RECEIPTS_DIR = ROOT / "Receipt demos"
DEFAULT_MODEL = "gemini-flash-latest"


def require_env(*names: str) -> str:
    for name in names:
        if value := os.getenv(name):
            return value
    sys.exit(f"Missing {' or '.join(names)} in .env")


def init_sentry() -> None:
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        spotlight=os.getenv("SENTRY_SPOTLIGHT", "1") != "0",
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=1.0,
        enable_logs=True,
        send_default_pii=False,
    )


def flush_sentry() -> None:
    sentry_sdk.flush()
    # sentry-sdk skips flushing batched logs when there is no DSN transport (Spotlight-only mode).
    client = sentry_sdk.get_client()
    if getattr(client, "transport", None) is None and getattr(client, "log_batcher", None) is not None:
        client.log_batcher.flush()


def process_folder(folder: Path, gemini: genai.Client, model: str, supabase, dry_run: bool) -> bool:
    """Returns False if the folder failed."""
    sentry_sdk.set_tag("receipt_folder", folder.name)
    images = list_images(folder)
    print(f"\n=== {folder.name}: {len(images)} images ===")
    if not images:
        print("  Skipped: no images.")
        sentry_logger.warning("Skipped receipt folder {folder}: no images", folder=folder.name)
        return True

    try:
        with sentry_sdk.start_span(op="gen_ai.extract", name="Gemini extraction") as span:
            span.set_data("image_count", len(images))
            span.set_data("model", model)
            receipt = extract_receipt(gemini, model, images)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        print(f"  Extraction failed: {exc}")
        return False

    extracted_date = receipt.purchase_date
    issues = reconcile_purchase_date(receipt) + check_totals(receipt)
    if receipt.purchase_date != extracted_date:
        print(f"  Corrected purchase date {extracted_date} -> {receipt.purchase_date} (printed {receipt.purchase_date_printed!r})")
        sentry_logger.warning(
            "Corrected purchase date for {folder}: {old} -> {new} (printed {printed})",
            folder=folder.name, old=extracted_date, new=receipt.purchase_date, printed=receipt.purchase_date_printed,
        )
    print(f"  {receipt.vendor_name} | {receipt.purchase_date} | {len(receipt.items)} items | "
          f"subtotal {receipt.subtotal} | tax {receipt.tax_total} | total {receipt.total}")
    for issue in issues:
        print(f"  WARNING: {issue}")
        sentry_logger.warning("Receipt {folder} needs review: {issue}", folder=folder.name, issue=issue)

    if dry_run:
        print(receipt.model_dump_json(indent=2))
        return True

    from receipts.store import save_receipt, upload_images

    try:
        with sentry_sdk.start_span(op="storage.upload", name="Upload receipt images"):
            paths = upload_images(supabase, folder.name, images)
        with sentry_sdk.start_span(op="db.upsert", name="Save receipt"):
            receipt_id = save_receipt(supabase, folder.name, receipt, model, paths, issues)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        print(f"  Saving failed: {exc}")
        return False

    print(f"  Saved receipt {receipt_id} ({len(paths)} images uploaded).")
    sentry_logger.info("Saved receipt {folder} as {receipt_id}", folder=folder.name, receipt_id=receipt_id)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=Path, default=DEFAULT_RECEIPTS_DIR, help="Folder containing one subfolder per receipt.")
    parser.add_argument("--folder", action="append", help="Only process this subfolder (repeatable).")
    parser.add_argument("--dry-run", action="store_true", help="Extract and print, without uploading or saving.")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    init_sentry()
    model = os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
    gemini = genai.Client(api_key=require_env("API_KEY"))

    supabase = None
    if not args.dry_run:
        from supabase import create_client
        from receipts.store import SetupError, ensure_ready

        supabase = create_client(
            require_env("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL"),
            require_env("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
        )
        try:
            ensure_ready(supabase)
        except SetupError as exc:
            sentry_sdk.capture_exception(exc)
            flush_sentry()
            sys.exit(str(exc))

    folders = sorted(p for p in args.dir.iterdir() if p.is_dir())
    if args.folder:
        wanted = {f.lower() for f in args.folder}
        folders = [f for f in folders if f.name.lower() in wanted]
    if not folders:
        sys.exit(f"No receipt folders found in {args.dir}")

    failures = 0
    for folder in folders:
        with sentry_sdk.isolation_scope(), sentry_sdk.start_transaction(op="receipt.process", name=f"process receipt {folder.name}"):
            if not process_folder(folder, gemini, model, supabase, args.dry_run):
                failures += 1

    flush_sentry()
    if failures:
        sys.exit(f"\n{failures} folder(s) failed.")


if __name__ == "__main__":
    main()
