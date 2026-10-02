"""Receipt-session storage. Phone captures and the future device both land here."""

from storage3.exceptions import StorageApiError
from supabase import Client

from .store import BUCKET, ensure_bucket, missing_bucket

MAX_IMAGES = 24
OPEN_STATUSES = {"capturing", "uploading", "failed"}


def ordered_image_rows(rows: list[dict]) -> list[dict]:
    """Sort receipt images from the top of the receipt to the bottom."""
    return sorted(rows, key=lambda row: (row["sequence_number"], row.get("created_at") or ""))


def image_extension(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return "jpg", "image/jpeg"


class SessionError(RuntimeError):
    pass


def _session_or_raise(session: dict | None) -> dict:
    if not session:
        raise SessionError("Receipt not found.")
    return session


def create_session(client: Client, restaurant_id: str) -> dict:
    result = client.table("receipt_sessions").insert({
        "restaurant_id": restaurant_id,
        "status": "capturing",
    }).execute()
    return result.data[0]


def get_session(client: Client, session_id: str, restaurant_id: str) -> dict | None:
    result = (
        client.table("receipt_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("restaurant_id", restaurant_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def set_status(client: Client, session_id: str, status: str, processed_at: str | None = None) -> None:
    patch: dict = {"status": status}
    if processed_at is not None:
        patch["processed_at"] = processed_at
    client.table("receipt_sessions").update(patch).eq("id", session_id).execute()


def list_session_images(client: Client, session_id: str) -> list[dict]:
    result = (
        client.table("receipt_images")
        .select("id, storage_path, sequence_number, image_url, created_at")
        .eq("receipt_session_id", session_id)
        .execute()
    )
    return ordered_image_rows(result.data or [])


def store_session_images(client: Client, restaurant_id: str, session_id: str, blobs: list[bytes]) -> int:
    """Stores original images for one receipt. Sequence follows the order they were captured."""
    if not blobs:
        raise SessionError("Take at least one photo before finishing.")
    if len(blobs) > MAX_IMAGES:
        raise SessionError(f"A receipt can have at most {MAX_IMAGES} photos.")

    session = _session_or_raise(get_session(client, session_id, restaurant_id))
    existing = list_session_images(client, session_id)
    if existing:
        return len(existing)
    if session["status"] not in OPEN_STATUSES:
        raise SessionError("This receipt can no longer accept photos.")

    set_status(client, session_id, "uploading")
    uploaded: list[str] = []
    try:
        ensure_bucket(client)
        bucket = client.storage.from_(BUCKET)
        for sequence, blob in enumerate(blobs, start=1):
            ext, content_type = image_extension(blob)
            path = f"{restaurant_id}/{session_id}/{sequence:03d}.{ext}"
            options = {"content-type": content_type, "upsert": "false"}
            try:
                bucket.upload(path, blob, file_options=options)
            except StorageApiError as exc:
                if not missing_bucket(exc):
                    raise
                ensure_bucket(client)
                bucket.upload(path, blob, file_options=options)
            uploaded.append(path)
        client.table("receipt_images").insert([
            {
                "receipt_session_id": session_id,
                "page_order": sequence,
                "sequence_number": sequence,
                "storage_path": path,
                "image_url": path,
            }
            for sequence, path in enumerate(uploaded, start=1)
        ]).execute()
    except Exception:
        if uploaded:
            client.storage.from_(BUCKET).remove(uploaded)
        client.table("receipt_images").delete().eq("receipt_session_id", session_id).execute()
        set_status(client, session_id, "capturing")
        raise
    return len(uploaded)


def download_ordered_images(client: Client, session_id: str) -> list[bytes]:
    rows = list_session_images(client, session_id)
    if not rows:
        raise SessionError("This receipt has no photos.")
    bucket = client.storage.from_(BUCKET)
    return [bucket.download(row["storage_path"]) for row in rows]


def ensure_restaurant(client: Client, owner_id: str, restaurant_name: str | None = None) -> dict:
    found = client.table("restaurants").select("*").eq("owner_id", owner_id).limit(1).execute()
    if found.data:
        return found.data[0]
    created = client.table("restaurants").insert({
        "owner_id": owner_id,
        "name": restaurant_name or "My Restaurant",
    }).execute()
    return created.data[0]
