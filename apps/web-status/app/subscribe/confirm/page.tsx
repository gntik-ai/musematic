import { Suspense } from "react";
import { TokenActionClient } from "@/components/TokenActionClient";

export default function ConfirmSubscriptionPage() {
  return (
    <Suspense fallback={null}>
      <TokenActionClient endpoint="confirm" title="Confirm subscription" />
    </Suspense>
  );
}
