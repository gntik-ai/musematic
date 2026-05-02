"use client";

import { Badge } from "@/components/ui/badge";

export function SubscriptionStatusBadge({ status }: { status: string }) {
  if (status === "active" || status === "trial") {
    return <Badge variant="secondary">{status}</Badge>;
  }
  if (status === "cancellation_pending" || status === "past_due") {
    return <Badge variant="outline">{status}</Badge>;
  }
  return <Badge variant="destructive">{status}</Badge>;
}
