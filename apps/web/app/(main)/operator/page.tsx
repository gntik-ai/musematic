"use client";

import { useMemo, useState } from "react";
import {
  Activity,
  BrainCircuit,
  Gauge,
  ShieldAlert,
} from "lucide-react";
import { ActiveExecutionsTable } from "@/components/features/operator/ActiveExecutionsTable";
import { AlertFeed } from "@/components/features/operator/AlertFeed";
import { AttentionFeedPanel } from "@/components/features/operator/AttentionFeedPanel";
import { ConnectionStatusBanner } from "@/components/features/operator/ConnectionStatusBanner";
import { OperatorMetricsGrid } from "@/components/features/operator/OperatorMetricsGrid";
import { QueueBacklogChart } from "@/components/features/operator/QueueBacklogChart";
import { ReasoningBudgetGauge } from "@/components/features/operator/ReasoningBudgetGauge";
import { ServiceHealthPanel } from "@/components/features/operator/ServiceHealthPanel";
import { Badge } from "@/components/ui/badge";
import { useActiveExecutions } from "@/lib/hooks/use-active-executions";
import { useOperatorMetrics } from "@/lib/hooks/use-operator-metrics";
import { useQueueLag } from "@/lib/hooks/use-queue-lag";
import { useReasoningBudget } from "@/lib/hooks/use-reasoning-budget";
import { useServiceHealth } from "@/lib/hooks/use-service-health";
import { useAlertFeedStore } from "@/lib/stores/use-alert-feed-store";
import {
  DEFAULT_ACTIVE_EXECUTIONS_FILTERS,
  type ActiveExecutionsFilters,
} from "@/lib/types/operator-dashboard";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

const heroCards = [
  {
    icon: Activity,
    title: "Operational overview",
    description:
      "One surface for executions, service health, alerts and queue pressure.",
  },
  {
    icon: BrainCircuit,
    title: "Reasoning diagnostics",
    description:
      "Drill into traces, provenance and resource usage for any active run.",
  },
  {
    icon: ShieldAlert,
    title: "Escalation lane",
    description:
      "Live alerts and agent attention requests stay visible while you triage.",
  },
];

export default function OperatorDashboardPage() {
  const [filters, setFilters] = useState<ActiveExecutionsFilters>(
    DEFAULT_ACTIVE_EXECUTIONS_FILTERS,
  );
  const workspaceId =
    useWorkspaceStore((state) => state.currentWorkspace?.id ?? null) ??
    useAuthStore((state) => state.user?.workspaceId ?? null);
  const metricsQuery = useOperatorMetrics();
  const serviceHealthQuery = useServiceHealth();
  const activeExecutionsQuery = useActiveExecutions(workspaceId, filters);
  const queueLagQuery = useQueueLag();
  const reasoningBudgetQuery = useReasoningBudget();
  const isConnected = useAlertFeedStore((state) => state.isConnected);
  const queueTopics = useMemo(
    () => queueLagQuery.data?.topics ?? [],
    [queueLagQuery.data],
  );

  const updateFilters = (nextValues: Partial<ActiveExecutionsFilters>) => {
    setFilters((current) => ({ ...current, ...nextValues }));
  };

  return (
    <section className="space-y-6">
      <header className="overflow-hidden rounded-[2rem] border bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.18),transparent_26%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--muted)/0.55)_100%)] p-6 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <Badge className="w-fit bg-background/70 text-foreground" variant="outline">
              Platform operations
            </Badge>
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-border/60 bg-background/75 p-3">
                <Gauge className="h-5 w-5 text-brand-accent" />
              </div>
              <div className="space-y-1">
                <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
                  Operator Dashboard
                </h1>
                <p className="text-sm text-muted-foreground md:text-base">
                  Real-time operational diagnostics for execution flow, health,
                  alerts and budget pressure.
                </p>
              </div>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {heroCards.map((card) => (
              <div
                key={card.title}
                className="rounded-2xl border border-border/60 bg-background/75 p-4 shadow-sm"
              >
                <card.icon className="h-4 w-4 text-brand-accent" />
                <p className="mt-3 text-sm font-medium">{card.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {card.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </header>

      <ConnectionStatusBanner
        isConnected={isConnected}
        isPollingFallback={!isConnected}
      />

      <OperatorMetricsGrid
        isLoading={metricsQuery.isLoading}
        isStale={metricsQuery.isStale}
        metrics={metricsQuery.metrics}
      />

      <ServiceHealthPanel
        isLoading={serviceHealthQuery.isLoading}
        snapshot={serviceHealthQuery.snapshot}
      />

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-6">
          <ActiveExecutionsTable
            executions={activeExecutionsQuery.executions}
            filters={filters}
            isLoading={activeExecutionsQuery.isLoading}
            onFiltersChange={updateFilters}
            onRowClick={(executionId) => {
              window.location.assign(
                `/operator/executions/${encodeURIComponent(executionId)}`,
              );
            }}
            totalCount={activeExecutionsQuery.totalCount}
          />

          <div className="grid gap-6 lg:grid-cols-2">
            <QueueBacklogChart
              data={queueTopics}
              error={queueLagQuery.isError}
              isLoading={queueLagQuery.isLoading}
            />
            <ReasoningBudgetGauge
              error={reasoningBudgetQuery.isError}
              isLoading={reasoningBudgetQuery.isLoading}
              utilization={reasoningBudgetQuery.utilization}
            />
          </div>
        </div>

        <div className="space-y-6">
          <AlertFeed />
          <AttentionFeedPanel />
        </div>
      </div>
    </section>
  );
}
