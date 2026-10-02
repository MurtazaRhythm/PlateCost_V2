"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getReceipt } from "@/lib/api";
import { longDate, money } from "@/lib/format";
import type { Receipt } from "@/lib/types";

export function ReceiptView({ receiptId }: { receiptId: string }) {
  const router = useRouter();
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewer, setViewer] = useState(false);

  useEffect(() => {
    let active = true;
    getReceipt(receiptId)
      .then((row) => {
        if (active) setReceipt(row);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "This receipt could not be opened.");
      });
    return () => {
      active = false;
    };
  }, [receiptId]);

  if (error) {
    return (
      <div className="flex min-h-dvh flex-col justify-center px-6">
        <p>{error}</p>
        <button type="button" onClick={() => router.push("/")} className="mt-6 text-accent">
          Back to Dashboard
        </button>
      </div>
    );
  }

  if (!receipt) {
    return <p className="grid min-h-dvh place-items-center text-muted">Loading receipt…</p>;
  }

  const currency = receipt.currency || "USD";

  return (
    <div className="min-h-dvh px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(1.5rem,env(safe-area-inset-top))]">
      <p className="text-sm font-medium text-accent">Receipt Processed ✓</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{receipt.vendor || "Unknown vendor"}</h1>

      <dl className="mt-6 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
        <Row label="Date" value={longDate(receipt.date)} />
        <Row label="Subtotal" value={money(receipt.subtotal, currency)} />
        <Row label="Tax" value={money(receipt.tax, currency)} />
        {receipt.tip ? <Row label="Tip" value={money(receipt.tip, currency)} /> : null}
        <Row label="Total" value={money(receipt.total, currency)} strong />
        <Row label="Category" value={receipt.category || "—"} />
        {receipt.payment_method ? <Row label="Payment" value={receipt.payment_method} /> : null}
      </dl>

      {receipt.needs_review ? (
        <p className="mt-4 text-sm text-danger">Some totals need a quick check before you file this.</p>
      ) : null}

      <h2 className="mb-3 mt-8 text-sm font-medium text-muted">Items</h2>
      {receipt.items.length === 0 ? (
        <p className="text-muted">No line items were read.</p>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
          {receipt.items.map((item, index) => (
            <li key={`${item.name}-${index}`} className="flex items-start justify-between gap-4 px-4 py-3">
              <span>
                <span className="block">{item.name || "Item"}</span>
                {item.quantity != null && item.quantity !== 1 ? (
                  <span className="text-sm text-muted">Qty {item.quantity}</span>
                ) : null}
              </span>
              <span className="font-medium">{money(item.total_price, currency)}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-8 space-y-3">
        <button
          type="button"
          onClick={() => setViewer(true)}
          disabled={receipt.images.length === 0}
          className="h-12 w-full rounded-full border border-line bg-card font-semibold disabled:opacity-40"
        >
          View Original Receipt
        </button>
        <button
          type="button"
          onClick={() => router.push("/")}
          className="h-14 w-full rounded-full bg-accent font-semibold text-white"
        >
          Back to Dashboard
        </button>
      </div>

      {viewer ? <OriginalReceipt images={receipt.images} onClose={() => setViewer(false)} /> : null}
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 px-4 py-3">
      <dt className="text-sm text-muted">{label}</dt>
      <dd className={strong ? "text-lg font-semibold" : "font-medium"}>{value}</dd>
    </div>
  );
}

function OriginalReceipt({
  images,
  onClose,
}: {
  images: { sequence_number: number; image_url: string | null }[];
  onClose: () => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const slides = images.filter((image) => image.image_url);

  function scrollTo(next: number) {
    const bounded = Math.max(0, Math.min(slides.length - 1, next));
    const node = scroller.current;
    if (!node) return;
    node.scrollTo({ left: bounded * node.clientWidth, behavior: "smooth" });
    setIndex(bounded);
  }

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-black text-white">
      <header className="flex items-center justify-between px-4 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <button type="button" onClick={onClose} className="text-sm">
          Close
        </button>
        <p className="text-sm">
          {index + 1} of {slides.length}
        </p>
      </header>
      <div
        ref={scroller}
        onScroll={(event) => {
          const node = event.currentTarget;
          if (!node.clientWidth) return;
          setIndex(Math.round(node.scrollLeft / node.clientWidth));
        }}
        className="flex min-h-0 flex-1 snap-x snap-mandatory overflow-x-auto"
      >
        {slides.map((image) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={image.sequence_number}
            src={image.image_url || undefined}
            alt={`Original receipt section ${image.sequence_number}`}
            className="h-full w-full shrink-0 snap-center object-contain"
          />
        ))}
      </div>
      {slides.length > 1 ? (
        <div className="flex justify-between px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
          <button type="button" onClick={() => scrollTo(index - 1)} className="text-sm">
            Previous
          </button>
          <button type="button" onClick={() => scrollTo(index + 1)} className="text-sm">
            Next
          </button>
        </div>
      ) : (
        <div className="pb-[max(1rem,env(safe-area-inset-bottom))]" />
      )}
    </div>
  );
}
