"use client";

import { formatDistanceToNow } from "date-fns";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  ServiceHealthEntry,
  ServiceStatus,
} from "@/lib/types/operator-dashboard";

export interface ServiceHealthIndicatorProps {
  entry: ServiceHealthEntry;
}

const toneClasses: Record<ServiceStatus, string> = {
  healthy: "bg-emerald-500",
  degraded: "bg-amber-500",
  unhealthy: "bg-rose-500",
  unknown: "bg-slate-400",
};

const statusCopy: Record<ServiceStatus, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  unhealthy: "Unhealthy",
  unknown: "Unknown",
};

export function ServiceHealthIndicator({ entry }: ServiceHealthIndicatorProps) {
  const checkedAt = entry.checkedAt
    ? formatDistanceToNow(new Date(entry.checkedAt), { addSuffix: true })
    : "just now";
  const title = `${statusCopy[entry.status]} · ${
    entry.latencyMs === null ? "Latency unavailable" : `${entry.latencyMs} ms`
  } · checked ${checkedAt}`;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <div
            className="flex items-center justify-between rounded-xl border border-border/60 bg-background/70 px-4 py-3 text-left"
            title={title}
          >
            <div className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className={cn("h-3 w-3 rounded-full", toneClasses[entry.status])}
              />
              <div>
                <p className="font-medium">{entry.displayName}</p>
                <p className="text-xs text-muted-foreground">
                  {statusCopy[entry.status]}
                </p>
              </div>
            </div>
            <Badge className="font-mono" variant="outline">
              {entry.latencyMs === null ? "—" : `${entry.latencyMs}ms`}
            </Badge>
          </div>
        </TooltipTrigger>
        <TooltipContent>{title}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
