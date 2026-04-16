"use client";

import { Loader2 } from "lucide-react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";

export interface ConnectionStatusBannerProps {
  isConnected: boolean;
  isPollingFallback: boolean;
}

export function ConnectionStatusBanner({
  isConnected,
  isPollingFallback,
}: ConnectionStatusBannerProps) {
  if (isConnected) {
    return null;
  }

  return (
    <Alert className="border-amber-500/30 bg-amber-500/10">
      <div className="flex items-start gap-3">
        <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-amber-600" />
        <div>
          <AlertTitle>Live updates paused</AlertTitle>
          <AlertDescription>
            Live updates paused — reconnecting...
            {isPollingFallback ? " (polling every 30 seconds)" : null}
          </AlertDescription>
        </div>
      </div>
    </Alert>
  );
}
