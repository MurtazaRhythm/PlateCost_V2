import re
from datetime import date

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(description="Item name exactly as printed, expanded only if obviously abbreviated.")
    sku: str | None = Field(None, description="Item code, SKU or PLU if printed.")
    quantity: float | None = Field(None, description="Quantity or weight purchased. Use 1 if not printed.")
    unit: str | None = Field(None, description="Unit for the quantity, e.g. 'ea', 'kg', 'lb'.")
    unit_price: float | None = Field(None, description="Price per unit.")
    total_price: float | None = Field(None, description="Line total after any item-level discount. Negative for refunds/discount lines.")
    category: str | None = Field(None, description="Short category guess, e.g. 'produce', 'meat', 'dairy', 'dry goods', 'beverage', 'supplies'.")


class TaxLine(BaseModel):
    name: str | None = Field(None, description="Tax label as printed, e.g. 'HST', 'GST', 'PST'.")
    rate: float | None = Field(None, description="Tax rate as a percentage, e.g. 13 for 13%.")
    amount: float | None = Field(None, description="Tax amount charged.")


class Receipt(BaseModel):
    vendor_name: str | None = Field(None, description="Store brand name in Title Case without branch/location, e.g. 'Real Canadian Superstore', even if printed in all caps.")
    vendor_address: str | None = None
    vendor_phone: str | None = None
    receipt_number: str | None = Field(None, description="Receipt, invoice, transaction or order number.")
    purchase_date_printed: str | None = Field(None, description="The purchase date exactly as printed on the receipt, e.g. '26/09/04'.")
    purchase_date: str | None = Field(None, description="Purchase date in YYYY-MM-DD format.")
    purchase_time: str | None = Field(None, description="Purchase time in 24-hour HH:MM format.")
    currency: str | None = Field(None, description="ISO 4217 currency code, e.g. 'CAD', 'USD'.")
    items: list[LineItem] = Field(default_factory=list, description="Every purchased line, in printed order, each listed once.")
    subtotal: float | None = None
    discount_total: float | None = Field(None, description="Total of receipt-level discounts/savings, as a positive number.")
    taxes: list[TaxLine] = Field(default_factory=list)
    tax_total: float | None = None
    tip: float | None = None
    total: float | None = Field(None, description="Final amount paid.")
    payment_method: str | None = Field(None, description="e.g. 'Visa', 'Mastercard', 'Debit', 'Cash'.")
    card_last4: str | None = Field(None, description="Last 4 digits of the card if printed.")


def _date_candidates(printed: str, today: date) -> list[date]:
    parts = re.findall(r"\d+", printed)
    if len(parts) != 3:
        return []
    a, b, c = parts
    if len(a) == 4:
        orders = [(a, b, c)]
    elif len(c) == 4:
        orders = [(c, b, a), (c, a, b)]
    else:
        orders = [(a, b, c), (c, b, a), (c, a, b)]
    found = set()
    for y, m, d in orders:
        year = int(y) if len(y) == 4 else 2000 + int(y)
        try:
            candidate = date(year, int(m), int(d))
        except ValueError:
            continue
        if candidate <= today:
            found.add(candidate)
    return sorted(found)


def reconcile_purchase_date(receipt: Receipt, today: date | None = None) -> list[str]:
    """Checks purchase_date against the printed date text, correcting it in place when only one
    reading fits. Returns review notes for dates that could not be confirmed."""
    if not receipt.purchase_date_printed:
        return []
    today = today or date.today()
    candidates = _date_candidates(receipt.purchase_date_printed, today)
    try:
        extracted = date.fromisoformat(receipt.purchase_date) if receipt.purchase_date else None
    except ValueError:
        extracted = None

    if extracted in candidates:
        return []

    matching = [c for c in candidates if extracted and (c.month, c.day) == (extracted.month, extracted.day)]
    if len(matching) == 1 or len(candidates) == 1:
        fixed = (matching or candidates)[0]
        receipt.purchase_date = fixed.isoformat()
        return []
    return [f"Purchase date {receipt.purchase_date} does not match printed {receipt.purchase_date_printed!r}."]


def check_totals(receipt: Receipt, tolerance: float = 0.05) -> list[str]:
    """Returns human-readable problems with the extracted totals; empty if consistent."""
    issues: list[str] = []
    item_sum = round(sum(i.total_price or 0 for i in receipt.items), 2)

    if not receipt.items:
        issues.append("No line items extracted.")
    if receipt.total is None:
        issues.append("No total extracted.")

    if receipt.subtotal is not None and receipt.items and abs(item_sum - receipt.subtotal) > tolerance:
        issues.append(f"Items sum to {item_sum:.2f} but subtotal is {receipt.subtotal:.2f}.")

    tax_total = receipt.tax_total
    if tax_total is None and receipt.taxes:
        tax_total = round(sum(t.amount or 0 for t in receipt.taxes), 2)

    if receipt.subtotal is not None and receipt.total is not None:
        expected = receipt.subtotal + (tax_total or 0) + (receipt.tip or 0)
        if abs(expected - receipt.total) > tolerance:
            issues.append(f"Subtotal + tax + tip = {expected:.2f} but total is {receipt.total:.2f}.")

    return issues
