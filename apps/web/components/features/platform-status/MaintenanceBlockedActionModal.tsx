"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { MaintenanceBlockedError } from "@/lib/maintenance-blocked";

interface MaintenanceBlockedActionModalProps {
  error: MaintenanceBlockedError | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function secondsUntil(value: string | undefined): number {
  if (!value) {
    return 0;
  }
  return Math.max(0, Math.ceil((new Date(value).getTime() - Date.now()) / 1000));
}

function formatRetryLabel(baseLabel: string, seconds: number): string {
  if (seconds <= 0) {
    return baseLabel;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes <= 0) {
    return `${baseLabel} ${seconds}s`;
  }
  return `${baseLabel} ${minutes}m ${remainder}s`;
}

export function MaintenanceBlockedActionModal({
  error,
  onOpenChange,
  open,
}: MaintenanceBlockedActionModalProps) {
  const t = useTranslations("platformStatus");
  const [remainingSeconds, setRemainingSeconds] = useState(() =>
    secondsUntil(error?.windowEndAt),
  );

  useEffect(() => {
    setRemainingSeconds(secondsUntil(error?.windowEndAt));
    if (!open || !error?.windowEndAt) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      setRemainingSeconds(secondsUntil(error.windowEndAt));
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [error, open]);

  const endTime = useMemo(() => {
    if (!error?.windowEndAt) {
      return t("unknownEnd");
    }
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(error.windowEndAt));
  }, [error?.windowEndAt, t]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("blockedActionTitle")}</DialogTitle>
          <DialogDescription>
            {t("blockedActionExplanation", { date: endTime })}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("dismiss")}
          </Button>
          <Button
            disabled={remainingSeconds > 0}
            onClick={() => window.location.reload()}
          >
            {formatRetryLabel(t("retryAfter"), remainingSeconds)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
