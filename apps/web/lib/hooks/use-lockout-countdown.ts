"use client";

import { useEffect, useMemo, useRef, useState } from "react";

interface UseLockoutCountdownOptions {
  unlockAt: Date | null;
  onExpired: () => void;
}

interface LockoutCountdownState {
  remainingSeconds: number;
  remainingFormatted: string;
  isExpired: boolean;
}

function formatRemaining(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}:${String(remainder).padStart(2, "0")}`;
}

function getRemainingSeconds(unlockAt: Date | null): number {
  if (unlockAt === null) {
    return 0;
  }

  return Math.max(0, Math.ceil((unlockAt.getTime() - Date.now()) / 1000));
}

export function useLockoutCountdown({
  unlockAt,
  onExpired,
}: UseLockoutCountdownOptions): LockoutCountdownState {
  const [remainingSeconds, setRemainingSeconds] = useState(() =>
    getRemainingSeconds(unlockAt),
  );
  const expiredRef = useRef(false);

  useEffect(() => {
    const nextRemaining = getRemainingSeconds(unlockAt);
    expiredRef.current = false;
    setRemainingSeconds(nextRemaining);

    if (unlockAt === null || nextRemaining === 0) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      const remaining = getRemainingSeconds(unlockAt);
      setRemainingSeconds(remaining);

      if (remaining === 0 && !expiredRef.current) {
        expiredRef.current = true;
        window.clearInterval(intervalId);
        onExpired();
      }
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [onExpired, unlockAt]);

  return useMemo(
    () => ({
      remainingSeconds,
      remainingFormatted: formatRemaining(remainingSeconds),
      isExpired: remainingSeconds === 0,
    }),
    [remainingSeconds],
  );
}
