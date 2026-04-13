"use client";

import { AlertCircle, RotateCcw } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface SectionErrorProps {
  title?: string | undefined;
  message?: string | undefined;
  onRetry?: (() => void) | undefined;
}

export function SectionError({
  title = "Section unavailable",
  message = "This section could not be loaded right now.",
  onRetry,
}: SectionErrorProps) {
  return (
    <Alert className="border-destructive/30 bg-destructive/10">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="min-w-0 flex-1">
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </div>
        {onRetry ? (
          <Button
            className="shrink-0"
            onClick={onRetry}
            size="sm"
            variant="outline"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Retry
          </Button>
        ) : null}
      </div>
    </Alert>
  );
}
