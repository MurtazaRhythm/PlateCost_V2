export type CapturedPhoto = {
  id: string;
  blob: Blob;
  url: string;
};

const empty: CapturedPhoto[] = [];
const photos = new Map<string, CapturedPhoto[]>();
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

export function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getPhotos(sessionId: string) {
  return photos.get(sessionId) ?? empty;
}

export function addPhoto(sessionId: string, blob: Blob) {
  const photo: CapturedPhoto = {
    id: crypto.randomUUID(),
    blob,
    url: URL.createObjectURL(blob),
  };
  photos.set(sessionId, [...getPhotos(sessionId), photo]);
  emit();
}

export function removePhoto(sessionId: string, photoId: string) {
  const current = getPhotos(sessionId);
  const removed = current.find((photo) => photo.id === photoId);
  if (removed) URL.revokeObjectURL(removed.url);
  const next = current.filter((photo) => photo.id !== photoId);
  photos.set(sessionId, next.length ? next : empty);
  emit();
}
