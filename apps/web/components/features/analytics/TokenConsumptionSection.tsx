"use client";

import { useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { SectionError } from "@/components/features/home/SectionError";
import { TokenConsumptionChart } from "@/components/features/analytics/TokenConsumptionChart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatAnalyticsPeriod } from "@/lib/analytics";
import { analyticsQueryKeys, useAnalyticsUsage } from "@/lib/hooks/use-analytics-usage";
import type { AnalyticsFilters, TokenBarPoint } from "@/types/analytics";

interface TokenConsumptionSectionProps {
  filters: AnalyticsFilters;
}

export function TokenConsumptionSection({ filters }: TokenConsumptionSectionProps) {
  const queryClient = useQueryClient();
  const usageQuery = useAnalyticsUsage(filters);

  const { chartData, providers } = useMemo(() => {
    const byPeriod = new Map<string, TokenBarPoint>();
    const providerSet = new Set<string>();

    for (const item of usageQuery.data?.items ?? []) {
      const period = formatAnalyticsPeriod(item.period);
      const currentPoint = byPeriod.get(period) ?? { period };
      const currentValue =
        typeof currentPoint[item.provider] === "number"
          ? (currentPoint[item.provider] as number)
          : 0;

      currentPoint[item.provider] = currentValue + item.total_tokens;
      byPeriod.set(period, currentPoint);
      providerSet.add(item.provider);
    }

    return {
      chartData: [...byPeriod.values()],
      providers: [...providerSet],
    };
  }, [usageQuery.data?.items]);

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Token consumption</CardTitle>
        <p className="text-sm text-muted-foreground">
          Compare provider footprint and spot token spikes across the active window.
        </p>
      </CardHeader>
      <CardContent>
        {usageQuery.isPending ? (
          <Skeleton className="h-[280px] rounded-[1.25rem]" />
        ) : usageQuery.isError ? (
          <SectionError
            message="Token consumption data could not be loaded."
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
            title="Token consumption unavailable"
          />
        ) : (
          <TokenConsumptionChart data={chartData} providers={providers} />
        )}
      </CardContent>
    </Card>
  );
}
