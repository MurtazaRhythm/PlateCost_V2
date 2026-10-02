export function money(value: number | null | undefined, currency = "USD") {
  if (value == null || Number.isNaN(value)) return "—";
  const code = currency || "USD";
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: code }).format(value);
  } catch {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
  }
}

export function longDate(iso: string | null | undefined) {
  if (!iso) return "—";
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return iso;
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(year, month - 1, day));
}

export function receiptCount(count: number) {
  return count === 1 ? "1 receipt" : `${count} receipts`;
}

export function photoCount(count: number) {
  return count === 1 ? "1 photo" : `${count} photos`;
}

export function recentWhen(receipt: { time: string | null; date: string | null; created_at: string }) {
  const created = new Date(receipt.created_at);
  const now = new Date();
  const sameDay =
    created.getFullYear() === now.getFullYear() &&
    created.getMonth() === now.getMonth() &&
    created.getDate() === now.getDate();

  if (sameDay && receipt.time) {
    const [hour, minute] = receipt.time.split(":").map(Number);
    const stamp = new Date();
    stamp.setHours(hour || 0, minute || 0, 0, 0);
    return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(stamp);
  }
  if (sameDay) {
    return new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(created);
  }
  if (receipt.date) return longDate(receipt.date);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(created);
}
