"use client";

import { differenceInDays, parseISO } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { CERTIFICATION_STATUS_LABELS, type CertificationStatus } from "@/lib/types/trust-workbench";
import { cn } from "@/lib/utils";

export interface CertificationStatusBadgeProps {
  status: CertificationStatus | "expiring";
  expiresAt?: string | null;
  size?: "sm" | "md";
}

const toneClasses: Record<CertificationStatus | "expiring", string> = {
  pending: "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300",
  active: "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
  expiring: "border-orange-500/30 bg-orange-500/12 text-orange-700 dark:text-orange-300",
  expired: "border-border/80 bg-muted/70 text-muted-foreground",
  revoked: "border-destructive/30 bg-destructive/10 text-foreground",
  superseded: "border-border/80 bg-muted/70 text-muted-foreground",
};

const sizeClasses = {
  sm: "px-2 py-0.5 text-[11px]",
  md: "px-2.5 py-0.5 text-xs",
} as const;

export function CertificationStatusBadge({
  status,
  expiresAt = null,
  size = "md",
}: CertificationStatusBadgeProps) {
  const countdown =
    status === "expiring" && expiresAt
      ? Math.max(0, differenceInDays(parseISO(expiresAt), new Date()))
      : null;

  return (
    <Badge
      aria-label={`Certification status ${CERTIFICATION_STATUS_LABELS[status]}`}
      className={cn(
        "gap-1.5 border font-semibold",
        toneClasses[status],
        sizeClasses[size],
      )}
      variant={status === "revoked" ? "destructive" : "outline"}
    >
      <span>{CERTIFICATION_STATUS_LABELS[status]}</span>
      {countdown !== null ? <span>{countdown} days</span> : null}
    </Badge>
  );
}
