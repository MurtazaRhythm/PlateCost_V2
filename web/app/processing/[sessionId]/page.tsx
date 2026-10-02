import { AuthGate } from "@/components/AuthGate";
import { ProcessingScreen } from "@/components/ProcessingScreen";

export default async function ProcessingPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return (
    <AuthGate>
      <ProcessingScreen sessionId={sessionId} />
    </AuthGate>
  );
}
