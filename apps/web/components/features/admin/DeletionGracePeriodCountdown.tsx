"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

export function DeletionGracePeriodCountdown({
  scheduledDeletionAt,
  onCancel,
  disabled,
}: {
  scheduledDeletionAt: string | null | undefined;
  onCancel: () => void;
  disabled?: boolean;
}) {
  const target = useMemo(
    () => (scheduledDeletionAt ? new Date(scheduledDeletionAt).getTime() : null),
    [scheduledDeletionAt],
  );
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  if (target === null) {
    return null;
  }

  const remainingMs = Math.max(0, target - now);
  const hours = Math.floor(remainingMs / 3_600_000);
  const minutes = Math.floor((remainingMs % 3_600_000) / 60_000);
  const seconds = Math.floor((remainingMs % 60_000) / 1000);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-4">
      <span className="font-mono text-sm">
        {String(hours).padStart(2, "0")}:{String(minutes).padStart(2, "0")}:
        {String(seconds).padStart(2, "0")}
      </span>
      <Button disabled={disabled} onClick={onCancel} size="sm" type="button" variant="outline">
        Cancel deletion
      </Button>
    </div>
  );
}
