"use client";

import { useMemo } from "react";
import { SectionError } from "@/components/features/home/SectionError";
import { DriftChart } from "@/components/features/analytics/DriftChart";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAnalyticsPeriod } from "@/lib/analytics";
import { useAnalyticsUsage } from "@/lib/hooks/use-analytics-usage";
import { useDriftAlerts } from "@/lib/hooks/use-drift-alerts";
import type {
  AnalyticsFilters,
  DriftAlertResponse,
  DriftChartPoint,
} from "@/types/analytics";

interface DriftDashboardSectionProps {
  filters: AnalyticsFilters;
}

export function DriftDashboardSection({ filters }: DriftDashboardSectionProps) {
  const driftAlertsQuery = useDriftAlerts(filters.workspaceId);
  const usageQuery = useAnalyticsUsage(filters);

  const charts = useMemo(() => {
    const alertsByAgent = new Map<string, DriftAlertResponse[]>();

    for (const alert of driftAlertsQuery.data?.items ?? []) {
      const existing = alertsByAgent.get(alert.agent_fqn) ?? [];
      alertsByAgent.set(alert.agent_fqn, [...existing, alert]);
    }

    return [...alertsByAgent.entries()].map(([agentFqn, alerts]) => {
      const usagePeriods = (usageQuery.data?.items ?? [])
        .filter((item) => item.agent_fqn === agentFqn)
        .map((item) => item.period);
      const periodSet = new Set<string>(usagePeriods);
      for (const alert of alerts) {
        periodSet.add(alert.created_at);
      }

      const points = [...periodSet]
        .sort((left, right) => new Date(left).getTime() - new Date(right).getTime())
        .map<DriftChartPoint>((period) => {
          const matchingAlert = alerts.find(
            (alert) =>
              new Date(alert.created_at).toISOString().slice(0, 10) ===
              new Date(period).toISOString().slice(0, 10),
          );

          return {
            period: formatAnalyticsPeriod(period),
            value: matchingAlert?.recent_mean ?? null,
            baseline: alerts.at(0)?.historical_mean ?? 0,
            isAnomaly: Boolean(matchingAlert),
          };
        });

      return { agentFqn, points };
    });
  }, [driftAlertsQuery.data?.items, usageQuery.data?.items]);

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Behavioral drift</CardTitle>
        <p className="text-sm text-muted-foreground">
          Watch for per-agent quality degradation and anomaly events over time.
        </p>
      </CardHeader>
      <CardContent>
        {driftAlertsQuery.isPending || usageQuery.isPending ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <Skeleton className="h-[280px] rounded-[1.5rem]" />
            <Skeleton className="h-[280px] rounded-[1.5rem]" />
          </div>
        ) : driftAlertsQuery.isError ? (
          <SectionError
            message="Drift alerts could not be loaded."
            title="Drift dashboard unavailable"
          />
        ) : usageQuery.isError ? (
          <SectionError
            message="Usage data could not be loaded for drift charts."
            title="Drift chart data unavailable"
          />
        ) : charts.length === 0 ? (
          <EmptyState
            description="No behavioral drift alerts are active for the selected workspace."
            title="No drift detected"
          />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {charts.map((chart) => (
              <DriftChart
                key={chart.agentFqn}
                agentFqn={chart.agentFqn}
                data={chart.points}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
