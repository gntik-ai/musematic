"use client";

import { Badge } from "@/components/ui/badge";
import { FLEET_STATUS_LABELS, type FleetStatus } from "@/lib/types/fleet";
import { cn } from "@/lib/utils";

const statusClassNames: Record<FleetStatus, string> = {
  active:
    "border-emerald-200 bg-emerald-100 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
  degraded:
    "border-amber-200 bg-amber-100 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100",
  paused:
    "border-sky-200 bg-sky-100 text-sky-900 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-100",
  archived:
    "border-slate-200 bg-slate-100 text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100",
};

interface FleetStatusBadgeProps {
  status: FleetStatus;
}

export function FleetStatusBadge({ status }: FleetStatusBadgeProps) {
  return (
    <Badge
      className={cn("capitalize", statusClassNames[status])}
      role="status"
      variant="outline"
    >
      {FLEET_STATUS_LABELS[status]}
    </Badge>
  );
}

