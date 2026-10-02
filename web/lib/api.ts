import { supabase } from "./supabase";
import type { DashboardData, ProcessStage, Receipt, SessionInfo } from "./types";

async function authHeader() {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Sign in to continue.");
  return { Authorization: `Bearer ${token}` };
}

async function errorMessage(response: Response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (typeof body.message === "string") return body.message;
  } catch {
    /* The server sometimes returns an empty body. */
  }
  return "Something went wrong.";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const auth = await authHeader();
  headers.set("Authorization", auth.Authorization);
  const response = await fetch(path, { ...init, headers, cache: "no-store" });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json() as Promise<T>;
}

export function getDashboard() {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return request<DashboardData>(`/api/dashboard?tz=${encodeURIComponent(tz)}`);
}

export function createSession() {
  return request<{ id: string; status: string }>("/api/receipt-sessions", { method: "POST" });
}

export function getSession(sessionId: string) {
  return request<SessionInfo>(`/api/receipt-sessions/${sessionId}`);
}

export function getReceipt(receiptId: string) {
  return request<Receipt>(`/api/receipts/${receiptId}`);
}

export async function uploadImages(sessionId: string, blobs: Blob[]) {
  const body = new FormData();
  blobs.forEach((blob, index) => {
    const name = `${String(index + 1).padStart(3, "0")}.jpg`;
    body.append("files", blob, name);
  });
  return request<{ count: number }>(`/api/receipt-sessions/${sessionId}/images`, {
    method: "POST",
    body,
  });
}

export async function processReceipt(
  sessionId: string,
  onStage: (stage: ProcessStage) => void,
): Promise<Receipt> {
  const headers = await authHeader();
  const response = await fetch(`/api/receipt-sessions/${sessionId}/process`, {
    method: "POST",
    headers,
    cache: "no-store",
  });

  if (response.status === 409) {
    return waitForReceipt(sessionId, onStage);
  }
  if (!response.ok || !response.body) {
    throw new Error(await errorMessage(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let receipt: Receipt | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const event = /^event: (.+)$/m.exec(chunk)?.[1];
      const dataLine = chunk.split("\n").find((line) => line.startsWith("data: "));
      const data = dataLine ? JSON.parse(dataLine.slice(6)) : {};
      if (event === "stage" && isStage(data.stage)) onStage(data.stage);
      if (event === "done") receipt = data as Receipt;
      if (event === "error") {
        throw new Error(data.message || "We couldn't process this receipt.");
      }
    }
  }

  if (!receipt) throw new Error("We couldn't process this receipt.");
  return receipt;
}

async function waitForReceipt(sessionId: string, onStage: (stage: ProcessStage) => void) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const session = await getSession(sessionId);
    if (session.status === "completed" && session.receipt_id) {
      return getReceipt(session.receipt_id);
    }
    if (session.status === "failed") {
      throw new Error("We couldn't process this receipt.");
    }
    if (session.status === "processing") onStage("extracting");
  }
  throw new Error("We couldn't process this receipt.");
}

function isStage(value: unknown): value is ProcessStage {
  return value === "reading" || value === "extracting" || value === "categorizing" || value === "uploading";
}
