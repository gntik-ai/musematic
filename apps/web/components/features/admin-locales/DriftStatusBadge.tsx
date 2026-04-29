"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type DriftStatus = "current" | "in_grace" | "over_threshold";

interface DriftStatusBadgeProps {
  status: DriftStatus;
}

const statusLabels: Record<DriftStatus, string> = {
  current: "Current",
  in_grace: "In grace",
  over_threshold: "Over threshold",
};

const statusClassNames: Record<DriftStatus, string> = {
  current: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  in_grace: "border-warning/50 bg-warning/10 text-foreground",
  over_threshold: "border-destructive/50 bg-destructive/10 text-destructive",
};

export function DriftStatusBadge({ status }: DriftStatusBadgeProps) {
  return (
    <Badge className={cn("border", statusClassNames[status])} variant="outline">
      {statusLabels[status]}
    </Badge>
  );
}
