"""Shapes stored receipt rows into the mobile app's receipt object."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def as_number(value):
    if value is None or value == "":
        return None
    return float(value)


def signed_url(signed) -> str | None:
    if isinstance(signed, dict):
        return signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
    return None


def receipt_payload(row: dict, items: list[dict], images: list[dict]) -> dict:
    return {
        "id": row["id"],
        "receipt_session_id": row.get("receipt_session_id"),
        "vendor": row.get("vendor_name"),
        "date": row.get("purchase_date"),
        "subtotal": as_number(row.get("subtotal")),
        "tax": as_number(row.get("tax_total")),
        "tip": as_number(row.get("tip")),
        "total": as_number(row.get("total")),
        "payment_method": row.get("payment_method"),
        "category": row.get("category"),
        "currency": row.get("currency") or "USD",
        "needs_review": bool(row.get("needs_review")),
        "created_at": row.get("created_at"),
        "items": [
            {
                "name": item.get("name") or item.get("description"),
                "quantity": as_number(item.get("quantity")),
                "unit_price": as_number(item.get("unit_price")),
                "total_price": as_number(item.get("total_price")),
                "category": item.get("category"),
                "confidence": as_number(item.get("confidence")),
            }
            for item in items
        ],
        "images": [
            {
                "sequence_number": image["sequence_number"],
                "image_url": image.get("signed_url") or image.get("image_url"),
            }
            for image in images
        ],
    }


def local_day_bounds(tz_name: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    current = now.astimezone(tz) if now else datetime.now(tz)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def in_local_day(value: str | None, start: datetime, end: datetime) -> bool:
    if not value:
        return False
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=start.tzinfo)
    return start <= parsed.astimezone(start.tzinfo) < end


def dashboard_payload(restaurant_name: str, receipts: list[dict], tz_name: str, now: datetime | None = None) -> dict:
    start, end = local_day_bounds(tz_name, now)
    today = [row for row in receipts if in_local_day(row.get("created_at"), start, end)]
    currencies = [row.get("currency") or "USD" for row in today]
    currency = max(set(currencies), key=currencies.count) if currencies else "USD"
    return {
        "restaurant_name": restaurant_name,
        "today": {
            "total": round(sum(as_number(row.get("total")) or 0 for row in today), 2),
            "count": len(today),
            "currency": currency,
        },
        "recent": [
            {
                "id": row["id"],
                "vendor": row.get("vendor_name") or "Unknown vendor",
                "total": as_number(row.get("total")),
                "currency": row.get("currency") or "USD",
                "date": row.get("purchase_date"),
                "time": _clock(row.get("purchase_time")),
                "created_at": row.get("created_at"),
            }
            for row in receipts[:8]
        ],
    }


def _clock(value) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:5] if len(text) >= 5 else text

