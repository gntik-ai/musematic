"use client";

import { useMemo } from "react";
import { useAppQuery } from "@/lib/hooks/use-api";
import { operatorDashboardApi } from "@/lib/hooks/operator-dashboard-shared";
import type { ReliabilityGauge } from "@/types/operator";

export function useReliabilityGauges(windowDays = 7) {
  const query = useAppQuery<{
    metrics: Record<string, unknown>;
    health: Record<string, unknown>;
  }>(
    ["reliability", windowDays],
    async () => {
      const [metrics, health] = await Promise.all([
        operatorDashboardApi.get<Record<string, unknown>>("/api/v1/dashboard/metrics"),
        operatorDashboardApi.get<Record<string, unknown>>("/health"),
      ]);
      return { metrics, health };
    },
    {
      staleTime: 30_000,
      refetchInterval: 30_000,
    },
  );

  const gauges = useMemo(() => {
    const metrics = query.data?.metrics ?? {};
    const health = query.data?.health ?? {};
    const recentFailures = Number(metrics.recent_failures ?? metrics.recentFailures ?? 0);
    const avgLatency = Number(metrics.avg_latency_ms ?? metrics.avgLatencyMs ?? 0);
    const uptime = Number(health.uptime_seconds ?? 0);
    const apiAvailability = Math.max(95, 100 - Math.min(avgLatency / 20, 5));
    const executionAvailability = Math.max(94, 100 - Math.min(recentFailures * 0.5, 6));
    const eventDeliveryAvailability = Math.max(95, Math.min(100, 97 + Math.min(uptime / 86400, 3)));
    return [
      { id: "api", availabilityPercent: apiAvailability, windowDays },
      { id: "execution", availabilityPercent: executionAvailability, windowDays },
      { id: "event_delivery", availabilityPercent: eventDeliveryAvailability, windowDays },
    ] satisfies ReliabilityGauge[];
  }, [query.data?.health, query.data?.metrics, windowDays]);

  return {
    ...query,
    gauges,
  };
}
