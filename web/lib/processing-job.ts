import { getPhotos } from "./capture-store";
import { getSession, processReceipt, uploadImages } from "./api";
import type { ProcessStage } from "./types";

export type JobState = {
  stage: ProcessStage;
  error: string | null;
  receiptId: string | null;
  running: boolean;
};

const idle: JobState = {
  stage: "uploading",
  error: null,
  receiptId: null,
  running: false,
};

const jobs = new Map<string, JobState>();
const started = new Set<string>();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function update(sessionId: string, patch: Partial<JobState>) {
  jobs.set(sessionId, { ...(jobs.get(sessionId) ?? idle), ...patch });
  emit();
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function jobSnapshot(sessionId: string) {
  return jobs.get(sessionId) ?? idle;
}

export function startProcessing(sessionId: string) {
  if (started.has(sessionId)) return;
  started.add(sessionId);
  update(sessionId, { stage: "uploading", error: null, receiptId: null, running: true });
  void run(sessionId);
}

export function retryProcessing(sessionId: string) {
  started.delete(sessionId);
  jobs.delete(sessionId);
  emit();
  startProcessing(sessionId);
}

async function run(sessionId: string) {
  try {
    const session = await getSession(sessionId);
    if (session.status === "completed" && session.receipt_id) {
      update(sessionId, { stage: "categorizing", running: false, receiptId: session.receipt_id });
      return;
    }

    if (session.image_count === 0) {
      const photos = getPhotos(sessionId);
      if (photos.length === 0) {
        throw new Error("Take at least one photo before finishing.");
      }
      update(sessionId, { stage: "uploading" });
      await uploadImages(
        sessionId,
        photos.map((photo) => photo.blob),
      );
    }

    update(sessionId, { stage: "reading" });
    const receipt = await processReceipt(sessionId, (stage) => {
      if (stage === "uploading") return;
      update(sessionId, { stage });
    });
    update(sessionId, { stage: "categorizing", running: false, receiptId: receipt.id, error: null });
  } catch (error) {
    const message = error instanceof Error ? error.message : "We couldn't process this receipt.";
    update(sessionId, { running: false, error: message });
    started.delete(sessionId);
  }
}
