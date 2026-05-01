"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Activity, BrainCircuit, Gauge, ShieldAlert, Siren } from "lucide-react";
import { ActiveExecutionsTable } from "@/components/features/operator/ActiveExecutionsTable";
import { AlertFeed } from "@/components/features/operator/AlertFeed";
import { AttentionFeedPanel } from "@/components/features/operator/AttentionFeedPanel";
import { ConnectionStatusBanner } from "@/components/features/operator/ConnectionStatusBanner";
import { DecommissionWizard } from "@/components/features/operator/decommission-wizard";
import { CapacityPanel, MaintenancePanel, RegionsPanel } from "@/components/features/multi-region-ops";
import { OperatorMetricsGrid } from "@/components/features/operator/OperatorMetricsGrid";
import { QueueBacklogChart } from "@/components/features/operator/QueueBacklogChart";
import { ReasoningBudgetGauge } from "@/components/features/operator/ReasoningBudgetGauge";
import { ReliabilityGauges } from "@/components/features/operator/reliability-gauges";
import { ServiceHealthPanel } from "@/components/features/operator/ServiceHealthPanel";
import { VerdictFeed } from "@/components/features/operator/verdict-feed";
import { WarmPoolPanel } from "@/components/features/operator/warm-pool-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useActiveExecutions } from "@/lib/hooks/use-active-executions";
import { useAgents } from "@/lib/hooks/use-agents";
import { useOperatorMetrics } from "@/lib/hooks/use-operator-metrics";
import { useQueueLag } from "@/lib/hooks/use-queue-lag";
import { useReasoningBudget } from "@/lib/hooks/use-reasoning-budget";
import { useServiceHealth } from "@/lib/hooks/use-service-health";
import { useAlertFeedStore } from "@/lib/stores/use-alert-feed-store";
import { DEFAULT_ACTIVE_EXECUTIONS_FILTERS, type ActiveExecutionsFilters } from "@/lib/types/operator-dashboard";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

const heroCards = [
  { icon: Activity, title: "Operational overview", description: "One surface for executions, service health, alerts and queue pressure." },
  { icon: BrainCircuit, title: "Reasoning diagnostics", description: "Drill into traces, provenance and resource usage for any active run." },
  { icon: ShieldAlert, title: "Escalation lane", description: "Live alerts and agent attention requests stay visible while you triage." },
];
const PANELS = ["warm-pool", "verdicts", "reliability", "regions", "maintenance", "capacity"] as const;
type OperatorPanel = (typeof PANELS)[number];

function resolvePanel(value: string | null): OperatorPanel {
  return PANELS.includes(value as OperatorPanel) ? (value as OperatorPanel) : "warm-pool";
}

export default function OperatorDashboardPage() {
  const [filters, setFilters] = useState<ActiveExecutionsFilters>(DEFAULT_ACTIVE_EXECUTIONS_FILTERS);
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null) ?? useAuthStore((state) => state.user?.workspaceId ?? null);
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activePanel = resolvePanel(searchParams.get("panel") ?? searchParams.get("tab"));
  const metricsQuery = useOperatorMetrics();
  const serviceHealthQuery = useServiceHealth();
  const activeExecutionsQuery = useActiveExecutions(workspaceId, filters);
  const queueLagQuery = useQueueLag();
  const reasoningBudgetQuery = useReasoningBudget();
  const agentsQuery = useAgents({}, { enabled: true, workspaceId });
  const isConnected = useAlertFeedStore((state) => state.isConnected);
  const queueTopics = useMemo(() => queueLagQuery.data?.topics ?? [], [queueLagQuery.data]);
  const [decommissionTarget, setDecommissionTarget] = useState<string | null>(null);

  const updateFilters = (nextValues: Partial<ActiveExecutionsFilters>) => {
    setFilters((current) => ({ ...current, ...nextValues }));
  };

  const setPanel = (panel: OperatorPanel) => {
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("panel", panel);
    router.replace(`${pathname}?${nextParams.toString()}`);
  };

  return (
    <section className="space-y-6">
      <header className="overflow-hidden rounded-[2rem] border bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.18),transparent_26%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--muted)/0.55)_100%)] p-6 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <Badge className="w-fit bg-background/70 text-foreground" variant="outline">Platform operations</Badge>
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-border/60 bg-background/75 p-3"><Gauge className="h-5 w-5 text-brand-accent" /></div>
              <div className="space-y-1">
                <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Operator Dashboard</h1>
                <p className="text-sm text-muted-foreground md:text-base">Real-time operational diagnostics for execution flow, health, alerts and budget pressure.</p>
              </div>
            </div>
          </div>
          <Button asChild variant="outline">
            <Link href="/operator/incidents">
              <Siren className="h-4 w-4" />
              Incidents
            </Link>
          </Button>
          <div className="grid gap-3 sm:grid-cols-3">
            {heroCards.map((card) => (
              <div key={card.title} className="rounded-2xl border border-border/60 bg-background/75 p-4 shadow-sm"><card.icon className="h-4 w-4 text-brand-accent" /><p className="mt-3 text-sm font-medium">{card.title}</p><p className="mt-1 text-xs text-muted-foreground">{card.description}</p></div>
            ))}
          </div>
        </div>
      </header>

      <ConnectionStatusBanner isConnected={isConnected} isPollingFallback={!isConnected} />
      <OperatorMetricsGrid isLoading={metricsQuery.isLoading} isStale={metricsQuery.isStale} metrics={metricsQuery.metrics} />
      <ServiceHealthPanel isLoading={serviceHealthQuery.isLoading} snapshot={serviceHealthQuery.snapshot} />

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-6">
          <ActiveExecutionsTable
            executions={activeExecutionsQuery.executions}
            filters={filters}
            isLoading={activeExecutionsQuery.isLoading}
            onFiltersChange={updateFilters}
            onRowClick={(executionId) => {
              window.location.assign(`/operator/executions/${encodeURIComponent(executionId)}`);
            }}
            totalCount={activeExecutionsQuery.totalCount}
          />
          <div className="grid gap-6 lg:grid-cols-2">
            <QueueBacklogChart data={queueTopics} error={queueLagQuery.isError} isLoading={queueLagQuery.isLoading} />
            <ReasoningBudgetGauge error={reasoningBudgetQuery.isError} isLoading={reasoningBudgetQuery.isLoading} utilization={reasoningBudgetQuery.utilization} />
          </div>
        </div>
        <div className="space-y-6">
          <AlertFeed />
          <AttentionFeedPanel />
        </div>
      </div>

      <div className="space-y-4 rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Expanded operator panels</h2>
            <p className="text-sm text-muted-foreground">Warm pool health, governance verdicts, reliability and regional operations stay one click away.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {PANELS.map((panel) => (
              <Button key={panel} variant={activePanel === panel ? "default" : "outline"} onClick={() => setPanel(panel)}>
                {panel}
              </Button>
            ))}
          </div>
        </div>
        {activePanel === "warm-pool" ? <WarmPoolPanel /> : null}
        {activePanel === "verdicts" ? <VerdictFeed workspaceId={workspaceId} /> : null}
        {activePanel === "reliability" ? <ReliabilityGauges /> : null}
        {activePanel === "regions" ? <RegionsPanel /> : null}
        {activePanel === "maintenance" ? <MaintenancePanel /> : null}
        {activePanel === "capacity" ? <CapacityPanel workspaceId={workspaceId} /> : null}
      </div>

      <div className="space-y-4 rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
        <div>
          <h2 className="text-xl font-semibold">Agent decommission</h2>
          <p className="text-sm text-muted-foreground">Trigger the 3-stage decommission flow directly from the operator surface.</p>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {agentsQuery.agents.slice(0, 6).map((agent) => (
            <div key={agent.fqn} className="rounded-2xl border border-border/70 bg-background/70 p-4">
              <p className="font-medium">{agent.name}</p>
              <p className="mt-1 text-sm text-muted-foreground">{agent.fqn}</p>
              <div className="mt-4">
                <Button variant="outline" onClick={() => setDecommissionTarget(agent.fqn)}>
                  Decommission Agent
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {decommissionTarget ? (
        <DecommissionWizard agentFqn={decommissionTarget} isOpen={Boolean(decommissionTarget)} onClose={() => setDecommissionTarget(null)} />
      ) : null}
    </section>
  );
}
