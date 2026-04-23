"use client";

import { useMemo } from "react";
import { useAppQuery } from "@/lib/hooks/use-api";
import { operatorDashboardApi } from "@/lib/hooks/operator-dashboard-shared";
import type { WarmPoolProfile } from "@/types/operator";

function deriveDeltaStatus(target: number, actual: number): WarmPoolProfile["deltaStatus"] {
  if (actual >= target) {
    return "on_target";
  }
  if (target > 0 && actual / target >= 0.8) {
    return "within_20_percent";
  }
  return "below_target";
}

export function useWarmPoolStatus() {
  const query = useAppQuery<{ keys?: Array<Record<string, unknown>> }>(
    ["warm-pool"],
    () => operatorDashboardApi.get("/api/v1/executions/runtime/warm-pool/status"),
    {
      staleTime: 10_000,
      refetchInterval: 10_000,
    },
  );

  const profiles = useMemo(() => {
    return (query.data?.keys ?? []).map((item) => {
      const name = String(item.agent_type ?? "profile");
      const targetReplicas = Number(item.target_size ?? 0);
      const actualReplicas = Number(item.available_count ?? 0) + Number(item.dispatched_count ?? 0);
      return {
        name,
        targetReplicas,
        actualReplicas,
        deltaStatus: deriveDeltaStatus(targetReplicas, actualReplicas),
        lastScalingEvents: [
          {
            at: String(item.last_dispatch_at ?? new Date(0).toISOString()),
            from: Number(item.warming_count ?? 0),
            to: actualReplicas,
            reason: "Warm pool status sync",
          },
        ],
      } satisfies WarmPoolProfile;
    });
  }, [query.data?.keys]);

  return {
    ...query,
    profiles,
  };
}
