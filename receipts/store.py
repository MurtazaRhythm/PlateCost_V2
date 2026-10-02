import mimetypes
from datetime import date, datetime, time, timezone
from pathlib import Path

from postgrest.exceptions import APIError
from storage3.exceptions import StorageApiError
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


def missing_bucket(exc: StorageApiError) -> bool:
    return "not found" in (exc.message or "").lower()


def ensure_bucket(client: Client) -> None:
    """Creates the receipts bucket when uploads would fail with StorageApiError: Bucket not found.

    Listing buckets by name is not enough: upload addresses the bucket by id.
    """
    try:
        client.storage.get_bucket(BUCKET)
        return
    except StorageApiError as exc:
        if not missing_bucket(exc):
            raise
    try:
        client.storage.create_bucket(BUCKET, options={"public": False})
    except StorageApiError as exc:
        if "already exists" not in (exc.message or "").lower() and "duplicate" not in (exc.message or "").lower():
            raise


def ensure_ready(client: Client) -> None:
    """Creates the storage bucket if needed and verifies the tables from supabase/schema.sql exist."""
    ensure_bucket(client)

    missing = []
    for table in ("receipts", "receipt_items", "receipt_taxes", "receipt_images", "receipt_sessions", "restaurants"):
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
    ensure_bucket(client)
    bucket = client.storage.from_(BUCKET)
    paths = []
    for path in images:
        storage_path = f"{folder_name}/{path.name}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        payload = path.read_bytes()
        options = {"content-type": content_type, "upsert": "true"}
        try:
            bucket.upload(storage_path, payload, file_options=options)
        except StorageApiError as exc:
            if not missing_bucket(exc):
                raise
            ensure_bucket(client)
            bucket.upload(storage_path, payload, file_options=options)
        paths.append(storage_path)
    return paths


def receipt_row(folder_name: str, receipt: Receipt, model: str, review_notes: list[str]) -> tuple[dict, list[str]]:
    purchase_date = _iso_or_none(receipt.purchase_date, date.fromisoformat)
    purchase_time = _iso_or_none(receipt.purchase_time, time.fromisoformat)
    notes = list(review_notes)
    if receipt.purchase_date and not purchase_date:
        notes.append(f"Unparseable purchase_date: {receipt.purchase_date!r}")
    if receipt.purchase_time and not purchase_time:
        notes.append(f"Unparseable purchase_time: {receipt.purchase_time!r}")

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
        "category": receipt.category,
        "needs_review": bool(notes),
        "review_notes": notes or None,
        "raw_extraction": receipt.model_dump(mode="json"),
        "model": model,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return row, notes


def _replace_children(client: Client, receipt_id: str, receipt: Receipt, image_paths: list[str] | None) -> None:
    tables = ["receipt_items", "receipt_taxes"]
    if image_paths is not None:
        tables.append("receipt_images")
    for table in tables:
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
            {
                "receipt_id": receipt_id,
                "page_order": n,
                "sequence_number": n,
                "storage_path": p,
                "image_url": p,
            }
            for n, p in enumerate(image_paths, start=1)
        ]).execute()


def save_receipt(
    client: Client,
    folder_name: str,
    receipt: Receipt,
    model: str,
    image_paths: list[str],
    review_notes: list[str],
) -> str:
    row, _notes = receipt_row(folder_name, receipt, model, review_notes)
    result = client.table("receipts").upsert(row, on_conflict="source_folder").execute()
    receipt_id = result.data[0]["id"]
    _replace_children(client, receipt_id, receipt, image_paths)
    return receipt_id


def save_session_receipt(
    client: Client,
    session_id: str,
    receipt: Receipt,
    model: str,
    review_notes: list[str],
) -> str:
    """Saves Gemini output for a capture session without replacing the original images."""
    row, _notes = receipt_row(f"session:{session_id}", receipt, model, review_notes)
    row["receipt_session_id"] = session_id
    existing = client.table("receipts").select("id").eq("receipt_session_id", session_id).limit(1).execute()
    if existing.data:
        receipt_id = existing.data[0]["id"]
        client.table("receipts").update(row).eq("id", receipt_id).execute()
    else:
        receipt_id = client.table("receipts").insert(row).execute().data[0]["id"]

    _replace_children(client, receipt_id, receipt, None)
    client.table("receipt_images").update({"receipt_id": receipt_id}).eq("receipt_session_id", session_id).execute()
    return receipt_id
