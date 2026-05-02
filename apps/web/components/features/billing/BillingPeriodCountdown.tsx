"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { useCancelDowngrade } from "@/lib/hooks/use-plan-mutations";

export function BillingPeriodCountdown({
  workspaceId,
  periodEnd,
}: {
  workspaceId: string;
  periodEnd: string;
}) {
  const cancel = useCancelDowngrade(workspaceId);
  const endMs = useMemo(() => new Date(periodEnd).getTime(), [periodEnd]);
  const [remainingMs, setRemainingMs] = useState(() => Math.max(endMs - Date.now(), 0));

  useEffect(() => {
    const interval = window.setInterval(() => {
      setRemainingMs(Math.max(endMs - Date.now(), 0));
    }, 60_000);
    setRemainingMs(Math.max(endMs - Date.now(), 0));
    return () => window.clearInterval(interval);
  }, [endMs]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3 text-sm">
      <span>
        Scheduled change in {formatRemaining(remainingMs)} at {new Date(periodEnd).toLocaleString()}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={cancel.isPending}
        onClick={() => cancel.mutate(workspaceId)}
      >
        Cancel scheduled downgrade
      </Button>
    </div>
  );
}

function formatRemaining(valueMs: number) {
  const totalMinutes = Math.ceil(valueMs / 60_000);
  const days = Math.floor(totalMinutes / 1_440);
  const hours = Math.floor((totalMinutes % 1_440) / 60);
  const minutes = totalMinutes % 60;

  if (days > 0) {
    return `${days}d ${hours}h`;
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}
