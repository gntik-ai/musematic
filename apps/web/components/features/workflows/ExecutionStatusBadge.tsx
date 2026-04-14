"use client";

import { Badge } from "@/components/ui/badge";
import type { ExecutionStatus } from "@/types/execution";

const executionStatusStyles: Record<
  ExecutionStatus,
  { label: string; className: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  queued: {
    label: "Queued",
    className: "text-foreground",
    variant: "outline",
  },
  running: {
    label: "Running",
    className: "bg-brand-primary/15 text-brand-primary",
    variant: "default",
  },
  paused: {
    label: "Paused",
    className: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
    variant: "outline",
  },
  waiting_for_approval: {
    label: "Waiting for approval",
    className: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
    variant: "outline",
  },
  completed: {
    label: "Completed",
    className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    variant: "outline",
  },
  failed: {
    label: "Failed",
    className: "",
    variant: "destructive",
  },
  canceled: {
    label: "Canceled",
    className: "text-muted-foreground",
    variant: "outline",
  },
  compensating: {
    label: "Compensating",
    className: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
    variant: "outline",
  },
};

export function ExecutionStatusBadge({ status }: { status: ExecutionStatus }) {
  const config = executionStatusStyles[status];

  return (
    <Badge className={config.className} variant={config.variant}>
      {config.label}
    </Badge>
  );
}
