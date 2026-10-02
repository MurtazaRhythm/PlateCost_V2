"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { addPhoto, getPhotos, removePhoto, subscribe } from "@/lib/capture-store";
import { photoCount } from "@/lib/format";

export function CaptureFlow({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const photos = useSyncExternalStore(
    subscribe,
    () => getPhotos(sessionId),
    () => getPhotos(sessionId),
  );
  const [view, setView] = useState<"camera" | "gallery">("camera");
  const [confirming, setConfirming] = useState(false);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  function finish() {
    if (!photos.length || busy) return;
    setConfirming(false);
    setBusy(true);
    router.push(`/processing/${sessionId}`);
  }

  return (
    <div className={view === "camera" ? "min-h-dvh bg-[#101412] text-white" : "min-h-dvh bg-background text-foreground"}>
      {view === "camera" ? (
        <Camera
          sessionId={sessionId}
          count={photos.length}
          onBack={() => (photos.length ? setLeaveOpen(true) : router.push("/"))}
          onOpenGallery={() => setView("gallery")}
          onFinish={() => photos.length && setConfirming(true)}
        />
      ) : (
        <Gallery
          sessionId={sessionId}
          onBack={() => setView("camera")}
          onFinish={() => photos.length && setConfirming(true)}
        />
      )}

      {confirming ? (
        <Sheet
          title="Finish Receipt?"
          body={`${photoCount(photos.length)} will be processed.`}
          cancelLabel="Cancel"
          confirmLabel="Process Receipt"
          onCancel={() => setConfirming(false)}
          onConfirm={finish}
        />
      ) : null}

      {leaveOpen ? (
        <Sheet
          title="Leave this receipt?"
          body="Photos stay on this phone until you finish the receipt."
          cancelLabel="Keep capturing"
          confirmLabel="Leave"
          onCancel={() => setLeaveOpen(false)}
          onConfirm={() => router.push("/")}
        />
      ) : null}
    </div>
  );
}

function Camera({
  sessionId,
  count,
  onBack,
  onOpenGallery,
  onFinish,
}: {
  sessionId: string;
  count: number;
  onBack: () => void;
  onOpenGallery: () => void;
  onFinish: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [native, setNative] = useState(false);
  const [ready, setReady] = useState(false);
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let stream: MediaStream | null = null;

    async function start() {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        setNative(true);
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1920 },
            height: { ideal: 1080 },
          },
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        const video = videoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play();
        }
        setReady(true);
      } catch {
        if (!cancelled) setNative(true);
      }
    }

    void start();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  function captureFrame() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) {
      fileRef.current?.click();
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        addPhoto(sessionId, blob);
        setFlash(true);
        window.setTimeout(() => setFlash(false), 140);
      },
      "image/jpeg",
      0.92,
    );
  }

  function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) addPhoto(sessionId, file);
  }

  return (
    <div className="relative min-h-dvh overflow-hidden bg-[#101412]">
      {native ? (
        <div className="absolute inset-0 grid place-items-center px-10 text-center text-white/80">
          <p>Tap Capture to photograph the next section of the receipt.</p>
        </div>
      ) : (
        <video ref={videoRef} className="absolute inset-0 h-full w-full object-cover" playsInline muted autoPlay />
      )}
      <div className="pointer-events-none absolute inset-x-6 top-24 bottom-56 rounded-md border border-white/90 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
      {flash ? <div className="absolute inset-0 bg-white/70" /> : null}

      <header className="absolute inset-x-0 top-0 z-10 flex items-center gap-3 px-4 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <button type="button" onClick={onBack} className="text-lg" aria-label="Back">
          ←
        </button>
        <h1 className="text-base font-medium">Receipt Capture</h1>
      </header>

      <div className="absolute inset-x-0 bottom-0 z-10 flex flex-col items-center gap-4 px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-4">
        {count > 0 ? (
          <button type="button" onClick={onOpenGallery} className="text-sm">
            Photos captured: {count}
          </button>
        ) : (
          <p className="text-sm text-white/80">Photos captured: 0</p>
        )}
        <button
          type="button"
          aria-label="Capture"
          onClick={() => (native ? fileRef.current?.click() : captureFrame())}
          disabled={!native && !ready}
          className="grid size-20 place-items-center rounded-full border-4 border-white disabled:opacity-40"
        >
          <span className="size-14 rounded-full bg-white" />
        </button>
        <p className="-mt-2 text-sm">Capture</p>
        <button type="button" onClick={onFinish} disabled={count === 0} className="text-base disabled:opacity-40">
          Finish Receipt
        </button>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={onFile}
      />
    </div>
  );
}

function Gallery({
  sessionId,
  onBack,
  onFinish,
}: {
  sessionId: string;
  onBack: () => void;
  onFinish: () => void;
}) {
  const photos = useSyncExternalStore(
    subscribe,
    () => getPhotos(sessionId),
    () => getPhotos(sessionId),
  );

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center gap-3 px-4 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <button type="button" onClick={onBack} className="text-lg" aria-label="Back to camera">
          ←
        </button>
        <h1 className="text-base font-medium">Receipt Capture</h1>
      </header>

      <div className="flex-1 px-5 pb-8 pt-5">
        {photos.length === 0 ? (
          <p className="text-muted">No photos yet.</p>
        ) : (
          <ul className="grid grid-cols-2 gap-3">
            {photos.map((photo, index) => (
              <li key={photo.id} className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={photo.url}
                  alt={`Receipt section ${index + 1}`}
                  className="aspect-[3/4] w-full rounded-xl object-cover"
                />
                <span className="absolute left-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-xs font-medium text-white">
                  {index + 1}
                </span>
                <button
                  type="button"
                  onClick={() => removePhoto(sessionId, photo.id)}
                  className="absolute right-2 top-2 rounded-full bg-white/95 px-2 py-0.5 text-xs font-medium text-danger"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 text-sm text-muted">{photoCount(photos.length)}</p>
      </div>

      <div className="space-y-3 px-5 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <button
          type="button"
          onClick={onBack}
          className="h-12 w-full rounded-full border border-line bg-card font-semibold"
        >
          + Take Another
        </button>
        <button
          type="button"
          onClick={onFinish}
          disabled={photos.length === 0}
          className="h-14 w-full rounded-full bg-accent font-semibold text-white disabled:opacity-40"
        >
          Finish Receipt
        </button>
      </div>
    </div>
  );
}

function Sheet({
  title,
  body,
  cancelLabel,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  title: string;
  body: string;
  cancelLabel: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-30 flex items-end justify-center bg-black/45 p-4">
      <div className="w-full max-w-md rounded-2xl bg-card p-5 text-foreground">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-2 text-muted">{body}</p>
        <div className="mt-5 grid grid-cols-2 gap-3">
          <button type="button" onClick={onCancel} className="h-12 rounded-full border border-line font-semibold">
            {cancelLabel}
          </button>
          <button type="button" onClick={onConfirm} className="h-12 rounded-full bg-accent font-semibold text-white">
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
