"use client";

import { TimerReset } from "lucide-react";
import { useLockoutCountdown } from "@/lib/hooks/use-lockout-countdown";

interface LockoutMessageProps {
  onExpired: () => void;
  unlockAt: Date;
}

export function LockoutMessage({ onExpired, unlockAt }: LockoutMessageProps) {
  const { remainingFormatted } = useLockoutCountdown({
    unlockAt,
    onExpired,
  });

  return (
    <div
      className="rounded-2xl border border-warning/30 bg-warning/10 p-5"
      role="status"
    >
      <div className="flex items-start gap-3">
        <div className="rounded-full bg-warning/15 p-2 text-warning">
          <TimerReset className="h-4 w-4" />
        </div>
        <div className="space-y-1">
          <p className="font-medium">Account temporarily locked.</p>
          <p className="text-sm text-muted-foreground">
            Try again in{" "}
            <span aria-live="polite" className="font-semibold text-foreground">
              {remainingFormatted}
            </span>
            .
          </p>
        </div>
      </div>
    </div>
  );
}
