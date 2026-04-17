"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { fleetApi, fleetQueryKeys } from "@/lib/hooks/use-fleets";
import type { FleetActionResponse } from "@/lib/types/fleet";

interface FleetActionInput {
  fleetId: string;
}

async function invalidateFleetActionQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  fleetId: string,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: fleetQueryKeys.detail(fleetId) }),
    queryClient.invalidateQueries({ queryKey: fleetQueryKeys.health(fleetId) }),
    queryClient.invalidateQueries({ queryKey: fleetQueryKeys.members(fleetId) }),
    queryClient.invalidateQueries({ queryKey: ["fleet", "list"] }),
  ]);
}

export function usePauseFleet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fleetId }: FleetActionInput) =>
      fleetApi.post<FleetActionResponse>(
        `/api/v1/fleets/${encodeURIComponent(fleetId)}/pause`,
      ),
    onSuccess: async (_, variables) => {
      await invalidateFleetActionQueries(queryClient, variables.fleetId);
    },
  });
}

export function useResumeFleet() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fleetId }: FleetActionInput) =>
      fleetApi.post<FleetActionResponse>(
        `/api/v1/fleets/${encodeURIComponent(fleetId)}/resume`,
      ),
    onSuccess: async (_, variables) => {
      await invalidateFleetActionQueries(queryClient, variables.fleetId);
    },
  });
}

