"use client";

import { AuthGate } from "@/components/AuthGate";
import { Dashboard } from "@/components/Dashboard";

export default function HomePage() {
  return (
    <AuthGate>
      <Dashboard />
    </AuthGate>
  );
}
