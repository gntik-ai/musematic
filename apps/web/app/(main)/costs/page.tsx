"use client";

import { AlertTriangle, LineChart, ReceiptText, WalletCards } from "lucide-react";
import { AnomalyCard } from "@/components/features/cost-governance/AnomalyCard";
import { BudgetThresholdGauge } from "@/components/features/cost-governance/BudgetThresholdGauge";
import { CostBreakdownChart } from "@/components/features/cost-governance/CostBreakdownChart";
import { ForecastChart } from "@/components/features/cost-governance/ForecastChart";
import { EmptyState } from "@/components/shared/EmptyState";
import { MetricCard } from "@/components/shared/MetricCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useLatestForecast,
  useOpenAnomalies,
  useWorkspaceBudgets,
  useWorkspaceCostSummary,
} from "@/lib/api/costs";
import { useWorkspaceStore } from "@/store/workspace-store";

function money(cents: number | string | null | undefined): string {
  return `$${(Number(cents ?? 0) / 100).toFixed(2)}`;
}

export default function CostsPage() {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const summary = useWorkspaceCostSummary(workspaceId);
  const forecast = useLatestForecast(workspaceId);
  const anomalies = useOpenAnomalies(workspaceId);
  const budgets = useWorkspaceBudgets(workspaceId);
  const activeBudget = budgets.data?.[0];

  if (!workspaceId) {
    return (
      <section className="space-y-6">
        <EmptyState title="Costs unavailable" description="Select a workspace." />
      </section>
    );
  }

  const breakdown = [
    {
      label: "Current",
      model: (summary.data?.model_cost_cents ?? 0) / 100,
      compute: (summary.data?.compute_cost_cents ?? 0) / 100,
      storage: (summary.data?.storage_cost_cents ?? 0) / 100,
      overhead: (summary.data?.overhead_cost_cents ?? 0) / 100,
    },
  ];

  return (
    <section className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          isLoading={summary.isPending}
          title="Period spend"
          value={money(summary.data?.total_cost_cents)}
        />
        <MetricCard
          title="Budget"
          unit={activeBudget?.period_type}
          value={activeBudget ? money(activeBudget.budget_cents) : "$0.00"}
        />
        <MetricCard
          isLoading={forecast.isPending}
          title="Forecast"
          value={money(forecast.data?.forecast_cents)}
        />
        <MetricCard
          isLoading={anomalies.isPending}
          title="Open anomalies"
          value={anomalies.data?.length ?? 0}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ReceiptText className="h-4 w-4" />
              Cost breakdown
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CostBreakdownChart data={breakdown} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <WalletCards className="h-4 w-4" />
              Budget
            </CardTitle>
          </CardHeader>
          <CardContent>
            {activeBudget ? (
              <BudgetThresholdGauge
                budgetCents={activeBudget.budget_cents}
                currentSpendCents={summary.data?.total_cost_cents ?? 0}
                thresholds={activeBudget.soft_alert_thresholds}
              />
            ) : (
              <EmptyState title="No active budget" description="Create a budget in Costs > Budgets." />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <LineChart className="h-4 w-4" />
              Forecast
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ForecastChart forecast={forecast.data ?? null} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4" />
              Anomalies
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {anomalies.data?.length ? (
              anomalies.data.map((anomaly) => <AnomalyCard key={anomaly.id} anomaly={anomaly} />)
            ) : (
              <EmptyState title="No open anomalies" description="Current workspace is clear." />
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
