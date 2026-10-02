import { AuthGate } from "@/components/AuthGate";
import { ReceiptView } from "@/components/ReceiptView";

export default async function ReceiptPage({ params }: { params: Promise<{ receiptId: string }> }) {
  const { receiptId } = await params;
  return (
    <AuthGate>
      <ReceiptView receiptId={receiptId} />
    </AuthGate>
  );
}
