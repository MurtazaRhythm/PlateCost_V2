"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createSession, getDashboard } from "@/lib/api";
import { money, receiptCount, recentWhen } from "@/lib/format";
import { supabase } from "@/lib/supabase";
import type { DashboardData } from "@/lib/types";

export function Dashboard() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  async function load() {
    setError(null);
    try {
      setData(await getDashboard());
    } catch (err) {
      setError(err instanceof Error ? err.message : "PlateCost can't reach the server.");
    }
  }

  useEffect(() => {
    let active = true;
    getDashboard()
      .then((dashboard) => {
        if (active) setData(dashboard);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "PlateCost can't reach the server.");
      });
    return () => {
      active = false;
    };
  }, []);

  async function capture() {
    setStarting(true);
    setError(null);
    try {
      const session = await createSession();
      router.push(`/capture/${session.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The receipt could not be started.");
      setStarting(false);
    }
  }

  async function signOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-start justify-between px-5 pt-[max(1.5rem,env(safe-area-inset-top))]">
        <div>
          <p className="text-2xl font-semibold tracking-tight">PlateCost</p>
          {data?.restaurant_name ? (
            <p className="mt-1 text-sm text-muted">{data.restaurant_name}</p>
          ) : null}
        </div>
        <button type="button" onClick={signOut} className="text-sm text-muted">
          Sign out
        </button>
      </header>

      <main className="flex-1 px-5 pb-28 pt-8">
        <h1 className="text-sm font-medium text-muted">Today&apos;s Activity</h1>
        {error ? (
          <div className="mt-6 rounded-2xl border border-line bg-card p-4">
            <p>{error}</p>
            <button type="button" onClick={load} className="mt-3 text-sm font-semibold text-accent">
              Try again
            </button>
          </div>
        ) : data ? (
          <>
            <p className="mt-2 text-4xl font-semibold tracking-tight">
              {money(data.today.total, data.today.currency)}
            </p>
            <p className="mt-1 text-muted">{receiptCount(data.today.count)}</p>

            <h2 className="mb-3 mt-10 text-sm font-medium text-muted">Recent Receipts</h2>
            {data.recent.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-line px-4 py-8 text-center text-muted">
                Captured receipts will show up here.
              </p>
            ) : (
              <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-card">
                {data.recent.map((receipt) => (
                  <li key={receipt.id}>
                    <button
                      type="button"
                      onClick={() => router.push(`/receipts/${receipt.id}`)}
                      className="flex w-full items-center justify-between gap-4 px-4 py-3.5 text-left"
                    >
                      <span>
                        <span className="block font-medium">{receipt.vendor}</span>
                        <span className="mt-0.5 block text-sm text-muted">{recentWhen(receipt)}</span>
                      </span>
                      <span className="font-medium">{money(receipt.total, receipt.currency)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          <p className="mt-6 text-muted">Loading today&apos;s receipts…</p>
        )}
      </main>

      <div className="sticky bottom-0 bg-gradient-to-t from-background from-60% to-transparent px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-8">
        <button
          type="button"
          onClick={capture}
          disabled={starting}
          className="h-14 w-full rounded-full bg-accent text-lg font-semibold text-white disabled:opacity-60"
        >
          {starting ? "Starting…" : "+ Capture Receipt"}
        </button>
      </div>
    </div>
  );
}
