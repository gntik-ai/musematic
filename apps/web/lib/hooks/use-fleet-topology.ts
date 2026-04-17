"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import { fleetApi, fleetQueryKeys } from "@/lib/hooks/use-fleets";
import type { FleetTopologyVersion } from "@/lib/types/fleet";

interface FleetTopologyHistoryResponse {
  items: FleetTopologyVersion[];
}

export function useFleetTopology(fleetId: string | null | undefined) {
  return useAppQuery<FleetTopologyVersion | null>(
    fleetQueryKeys.topology(fleetId),
    async () => {
      const response = await fleetApi.get<FleetTopologyHistoryResponse>(
        `/api/v1/fleets/${encodeURIComponent(fleetId ?? "")}/topology/history`,
      );

      const current =
        response.items.find((entry) => entry.is_current) ??
        [...response.items].sort((left, right) => right.version - left.version)[0] ??
        null;

      return current;
    },
    {
      enabled: Boolean(fleetId),
    },
  );
}

