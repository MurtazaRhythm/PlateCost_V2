import { AuthGate } from "@/components/AuthGate";
import { CaptureFlow } from "@/components/CaptureFlow";

export default async function CapturePage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return (
    <AuthGate>
      <CaptureFlow sessionId={sessionId} />
    </AuthGate>
  );
}
