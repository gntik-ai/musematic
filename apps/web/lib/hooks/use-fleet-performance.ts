"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import { fleetApi, fleetQueryKeys } from "@/lib/hooks/use-fleets";
import type {
  FleetPerformanceProfile,
  PerformanceTimeRange,
} from "@/lib/types/fleet";
import { TIME_RANGE_MAP } from "@/lib/types/fleet";

interface FleetPerformanceHistoryResponse {
  items: FleetPerformanceProfile[];
}

function buildPerformancePath(fleetId: string, range: PerformanceTimeRange): string {
  const now = new Date();
  const hours = TIME_RANGE_MAP[range].hours;
  const periodStart = new Date(now.getTime() - hours * 60 * 60 * 1000);
  const searchParams = new URLSearchParams({
    period_start: periodStart.toISOString(),
    period_end: now.toISOString(),
    limit: "200",
  });

  return `/api/v1/fleets/${encodeURIComponent(fleetId)}/performance-profile/history?${searchParams.toString()}`;
}

export function useFleetPerformanceHistory(
  fleetId: string | null | undefined,
  range: PerformanceTimeRange,
) {
  return useAppQuery<FleetPerformanceProfile[]>(
    fleetQueryKeys.performance(fleetId, range),
    async () => {
      const response = await fleetApi.get<FleetPerformanceHistoryResponse>(
        buildPerformancePath(fleetId ?? "", range),
      );
      return response.items;
    },
    {
      enabled: Boolean(fleetId),
    },
  );
}

