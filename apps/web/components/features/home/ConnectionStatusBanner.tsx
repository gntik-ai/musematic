"use client";

import { Loader2 } from "lucide-react";

interface ConnectionStatusBannerProps {
  isConnected: boolean;
}

export function ConnectionStatusBanner({
  isConnected,
}: ConnectionStatusBannerProps) {
  if (isConnected) {
    return null;
  }

  return (
    <div
      aria-live="polite"
      className={[
        "sticky top-16 z-20 flex items-center gap-3 rounded-xl border",
        "border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950",
        "transition-all duration-300 dark:border-amber-900",
        "dark:bg-amber-950 dark:text-amber-100",
      ].join(" ")}
      role="status"
    >
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>Live updates paused — reconnecting…</span>
    </div>
  );
}
