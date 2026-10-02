"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { jobSnapshot, retryProcessing, startProcessing, subscribe } from "@/lib/processing-job";
import type { ProcessStage } from "@/lib/types";

const steps: { id: ProcessStage; label: string }[] = [
  { id: "uploading", label: "Uploading receipt" },
  { id: "reading", label: "Reading receipt" },
  { id: "extracting", label: "Extracting information" },
  { id: "categorizing", label: "Categorizing expenses" },
];

export function ProcessingScreen({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const job = useSyncExternalStore(
    subscribe,
    () => jobSnapshot(sessionId),
    () => jobSnapshot(sessionId),
  );

  useEffect(() => {
    startProcessing(sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (job.receiptId) router.replace(`/receipts/${job.receiptId}`);
  }, [job.receiptId, router]);

  if (job.error) {
    return (
      <div className="flex min-h-dvh flex-col justify-center px-6 pb-10">
        <h1 className="text-2xl font-semibold tracking-tight">We couldn&apos;t process this receipt.</h1>
        {job.error !== "We couldn't process this receipt." ? (
          <p className="mt-3 text-muted">{job.error}</p>
        ) : (
          <p className="mt-3 text-muted">The original photos are still saved.</p>
        )}
        <button
          type="button"
          onClick={() => retryProcessing(sessionId)}
          className="mt-8 h-14 rounded-full bg-accent font-semibold text-white"
        >
          Try Again
        </button>
        <button type="button" onClick={() => router.push("/")} className="mt-4 text-sm text-muted">
          Back to Dashboard
        </button>
      </div>
    );
  }

  const active = steps.findIndex((step) => step.id === job.stage);

  return (
    <div className="flex min-h-dvh flex-col justify-center px-6">
      <h1 className="text-2xl font-semibold tracking-tight">Processing Receipt</h1>
      <ol className="mt-8 space-y-4">
        {steps.map((step, index) => {
          const state = index < active ? "done" : index === active ? "active" : "waiting";
          return (
            <li key={step.id} className="flex items-center gap-3 text-lg">
              <StatusMark state={state} />
              <span className={state === "waiting" ? "text-muted" : undefined}>{step.label}</span>
            </li>
          );
        })}
      </ol>
      <p className="mt-8 text-muted">Please wait...</p>
    </div>
  );
}

function StatusMark({ state }: { state: "done" | "active" | "waiting" }) {
  if (state === "done") {
    return (
      <span className="grid size-6 place-items-center rounded-full bg-accent text-sm text-white" aria-hidden>
        ✓
      </span>
    );
  }
  if (state === "active") {
    return (
      <span className="grid size-6 place-items-center" aria-hidden>
        <span className="size-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      </span>
    );
  }
  return <span className="grid size-6 place-items-center text-muted" aria-hidden>○</span>;
}
