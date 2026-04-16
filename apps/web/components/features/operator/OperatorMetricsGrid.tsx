"use client";

import { Badge } from "@/components/ui/badge";
import { MetricCard } from "@/components/shared/MetricCard";
import { type OperatorMetrics } from "@/lib/types/operator-dashboard";
import { cn } from "@/lib/utils";

export interface OperatorMetricsGridProps {
  metrics: OperatorMetrics | undefined;
  isLoading: boolean;
  isStale?: boolean;
}

function MetricShell({
  title,
  value,
  unit,
  isLoading,
  isStale = false,
  danger = false,
}: {
  title: string;
  value: number | string;
  unit?: string | undefined;
  isLoading: boolean;
  isStale?: boolean;
  danger?: boolean;
}) {
  return (
    <div className="relative">
      {isStale ? (
        <Badge
          className="absolute right-4 top-4 z-10 border-amber-500/30 bg-amber-500/12 text-amber-700 dark:text-amber-300"
          variant="outline"
        >
          Stale
        </Badge>
      ) : null}
      <MetricCard
        className={cn(danger && "border-destructive/30 bg-destructive/5 shadow-none")}
        isLoading={isLoading}
        title={title}
        unit={unit}
        value={value}
      />
    </div>
  );
}

export function OperatorMetricsGrid({
  metrics,
  isLoading,
  isStale = false,
}: OperatorMetricsGridProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <MetricShell
        isLoading={isLoading}
        isStale={isStale}
        title="Active Executions"
        value={metrics?.activeExecutions ?? "—"}
      />
      <MetricShell
        isLoading={isLoading}
        isStale={isStale}
        title="Queued Steps"
        value={metrics?.queuedSteps ?? "—"}
      />
      <MetricShell
        danger={(metrics?.pendingApprovals ?? 0) > 0}
        isLoading={isLoading}
        isStale={isStale}
        title="Pending Approvals"
        value={metrics?.pendingApprovals ?? "—"}
      />
      <MetricShell
        danger={(metrics?.recentFailures ?? 0) > 0}
        isLoading={isLoading}
        isStale={isStale}
        title="Recent Failures (1h)"
        value={metrics?.recentFailures ?? "—"}
      />
      <MetricShell
        isLoading={isLoading}
        isStale={isStale}
        title="Avg Latency (p50)"
        unit="ms"
        value={metrics?.avgLatencyMs ?? "—"}
      />
      <MetricShell
        isLoading={isLoading}
        isStale={isStale}
        title="Fleet Health Score"
        value={metrics?.fleetHealthScore ?? "—"}
      />
    </div>
  );
}
