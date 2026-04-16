"use client";

import { Badge } from "@/components/ui/badge";
import {
  ACTIVE_EXECUTION_STATUS_LABELS,
  type ActiveExecutionStatus,
} from "@/lib/types/operator-dashboard";

export interface ActiveExecutionStatusBadgeProps {
  status: ActiveExecutionStatus;
}

const tone: Record<ActiveExecutionStatus, string> = {
  running:
    "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
  paused:
    "border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300",
  waiting_for_approval:
    "border-blue-500/30 bg-blue-500/12 text-blue-700 dark:text-blue-300",
  compensating:
    "border-orange-500/30 bg-orange-500/12 text-orange-700 dark:text-orange-300",
};

export function ActiveExecutionStatusBadge({
  status,
}: ActiveExecutionStatusBadgeProps) {
  return (
    <Badge
      aria-label={`Execution status ${ACTIVE_EXECUTION_STATUS_LABELS[status]}`}
      className={tone[status]}
      variant="outline"
    >
      {ACTIVE_EXECUTION_STATUS_LABELS[status]}
    </Badge>
  );
}
