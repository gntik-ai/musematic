"use client";

import { useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SectionError } from "@/components/features/home/SectionError";
import { CostOverviewChart } from "@/components/features/analytics/CostOverviewChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { analyticsQueryKeys, useAnalyticsUsage } from "@/lib/hooks/use-analytics-usage";
import { useAnalyticsStore } from "@/lib/stores/use-analytics-store";
import { formatAnalyticsPeriod } from "@/lib/analytics";
import type { AnalyticsFilters, BreakdownMode, CostChartPoint } from "@/types/analytics";

interface CostOverviewSectionProps {
  filters: AnalyticsFilters;
}

function breakdownKeyForMode(
  mode: BreakdownMode,
  item: { agent_fqn: string; model_id: string },
): string {
  switch (mode) {
    case "agent":
      return item.agent_fqn;
    case "model":
      return item.model_id;
    default:
      return "workspace_total";
  }
}

export function CostOverviewSection({ filters }: CostOverviewSectionProps) {
  const queryClient = useQueryClient();
  const breakdownMode = useAnalyticsStore((state) => state.breakdownMode);
  const setBreakdownMode = useAnalyticsStore((state) => state.setBreakdownMode);
  const usageQuery = useAnalyticsUsage(filters);

  const { chartData, seriesKeys } = useMemo(() => {
    const byPeriod = new Map<string, CostChartPoint>();
    const keys = new Set<string>();

    for (const item of usageQuery.data?.items ?? []) {
      const periodLabel = formatAnalyticsPeriod(item.period);
      const key = breakdownKeyForMode(breakdownMode, item);
      const currentPoint = byPeriod.get(periodLabel) ?? { period: periodLabel };
      const previousValue =
        typeof currentPoint[key] === "number" ? (currentPoint[key] as number) : 0;

      currentPoint[key] = previousValue + item.cost_usd;
      byPeriod.set(periodLabel, currentPoint);
      keys.add(key);
    }

    return {
      chartData: [...byPeriod.values()],
      seriesKeys: [...keys],
    };
  }, [breakdownMode, usageQuery.data?.items]);

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Cost overview</CardTitle>
        <p className="text-sm text-muted-foreground">
          Understand how spend shifts over time by workspace, agent or model.
        </p>
      </CardHeader>
      <CardContent>
        {usageQuery.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-9 w-72 rounded-xl" />
            <Skeleton className="h-[320px] rounded-[1.25rem]" />
          </div>
        ) : usageQuery.isError ? (
          <SectionError
            message="Cost overview data could not be loaded."
            onRetry={() => {
              void queryClient.invalidateQueries({
                queryKey: analyticsQueryKeys.usage(
                  filters.workspaceId,
                  filters.from,
                  filters.to,
                  filters.granularity,
                ),
              });
            }}
            title="Cost overview unavailable"
          />
        ) : (
          <CostOverviewChart
            breakdownMode={breakdownMode}
            data={chartData}
            onBreakdownChange={setBreakdownMode}
            seriesKeys={seriesKeys}
          />
        )}
      </CardContent>
    </Card>
  );
}
