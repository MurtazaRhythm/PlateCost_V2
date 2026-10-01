import mimetypes
from datetime import date, datetime, time, timezone
from pathlib import Path

from postgrest.exceptions import APIError
from supabase import Client

from .models import Receipt

BUCKET = "receipts"


def _iso_or_none(value: str | None, parse) -> str | None:
    if not value:
        return None
    try:
        return parse(value).isoformat()
    except ValueError:
        return None


class SetupError(RuntimeError):
    pass


def ensure_ready(client: Client) -> None:
    """Creates the storage bucket if needed and verifies the tables from supabase/schema.sql exist."""
    if not any(b.name == BUCKET for b in client.storage.list_buckets()):
        client.storage.create_bucket(BUCKET, options={"public": False})

    missing = []
    for table in ("receipts", "receipt_items", "receipt_taxes", "receipt_images"):
        try:
            client.table(table).select("id").limit(1).execute()
        except APIError as exc:
            if exc.code != "PGRST205":
                raise
            missing.append(table)
    if missing:
        raise SetupError(
            f"Supabase tables not found: {', '.join(missing)}. "
            "Run supabase/schema.sql in the Supabase SQL editor, then try again."
        )


def upload_images(client: Client, folder_name: str, images: list[Path]) -> list[str]:
    bucket = client.storage.from_(BUCKET)
    paths = []
    for path in images:
        storage_path = f"{folder_name}/{path.name}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        bucket.upload(storage_path, path.read_bytes(), file_options={"content-type": content_type, "upsert": "true"})
        paths.append(storage_path)
    return paths


def save_receipt(
    client: Client,
    folder_name: str,
    receipt: Receipt,
    model: str,
    image_paths: list[str],
    review_notes: list[str],
) -> str:
    purchase_date = _iso_or_none(receipt.purchase_date, date.fromisoformat)
    purchase_time = _iso_or_none(receipt.purchase_time, time.fromisoformat)
    if receipt.purchase_date and not purchase_date:
        review_notes = [*review_notes, f"Unparseable purchase_date: {receipt.purchase_date!r}"]
    if receipt.purchase_time and not purchase_time:
        review_notes = [*review_notes, f"Unparseable purchase_time: {receipt.purchase_time!r}"]

    row = {
        "source_folder": folder_name,
        "vendor_name": receipt.vendor_name,
        "vendor_address": receipt.vendor_address,
        "vendor_phone": receipt.vendor_phone,
        "receipt_number": receipt.receipt_number,
        "purchase_date": purchase_date,
        "purchase_time": purchase_time,
        "currency": receipt.currency,
        "subtotal": receipt.subtotal,
        "discount_total": receipt.discount_total,
        "tax_total": receipt.tax_total,
        "tip": receipt.tip,
        "total": receipt.total,
        "payment_method": receipt.payment_method,
        "card_last4": receipt.card_last4,
        "needs_review": bool(review_notes),
        "review_notes": review_notes or None,
        "raw_extraction": receipt.model_dump(mode="json"),
        "model": model,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = client.table("receipts").upsert(row, on_conflict="source_folder").execute()
    receipt_id = result.data[0]["id"]

    for table in ("receipt_items", "receipt_taxes", "receipt_images"):
        client.table(table).delete().eq("receipt_id", receipt_id).execute()

    if receipt.items:
        client.table("receipt_items").insert([
            {"receipt_id": receipt_id, "line_number": n, **item.model_dump()}
            for n, item in enumerate(receipt.items, start=1)
        ]).execute()

    if receipt.taxes:
        client.table("receipt_taxes").insert([
            {"receipt_id": receipt_id, **tax.model_dump()} for tax in receipt.taxes
        ]).execute()

    if image_paths:
        client.table("receipt_images").insert([
            {"receipt_id": receipt_id, "page_order": n, "storage_path": p}
            for n, p in enumerate(image_paths, start=1)
        ]).execute()

    return receipt_id
