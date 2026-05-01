import { Suspense } from "react";
import { TokenActionClient } from "@/components/TokenActionClient";

export default function UnsubscribePage() {
  return (
    <Suspense fallback={null}>
      <TokenActionClient endpoint="unsubscribe" title="Unsubscribe" />
    </Suspense>
  );
}
