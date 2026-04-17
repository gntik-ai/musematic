"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import { fleetApi, fleetQueryKeys } from "@/lib/hooks/use-fleets";
import type { FleetHealthProjection } from "@/lib/types/fleet";

export function useFleetHealth(fleetId: string | null | undefined) {
  return useAppQuery<FleetHealthProjection>(
    fleetQueryKeys.health(fleetId),
    () =>
      fleetApi.get<FleetHealthProjection>(
        `/api/v1/fleets/${encodeURIComponent(fleetId ?? "")}/health`,
      ),
    {
      enabled: Boolean(fleetId),
      refetchInterval: 30_000,
    },
  );
}

