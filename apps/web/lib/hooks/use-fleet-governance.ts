"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import { fleetApi, fleetQueryKeys } from "@/lib/hooks/use-fleets";
import type {
  FleetGovernanceChain,
  FleetOrchestrationRules,
  FleetPersonalityProfile,
} from "@/lib/types/fleet";

export function useFleetGovernance(fleetId: string | null | undefined) {
  return useAppQuery<FleetGovernanceChain>(
    fleetQueryKeys.governance(fleetId),
    () =>
      fleetApi.get<FleetGovernanceChain>(
        `/api/v1/fleets/${encodeURIComponent(fleetId ?? "")}/governance-chain`,
      ),
    {
      enabled: Boolean(fleetId),
    },
  );
}

export function useFleetOrchestration(fleetId: string | null | undefined) {
  return useAppQuery<FleetOrchestrationRules>(
    fleetQueryKeys.orchestration(fleetId),
    () =>
      fleetApi.get<FleetOrchestrationRules>(
        `/api/v1/fleets/${encodeURIComponent(fleetId ?? "")}/orchestration-rules`,
      ),
    {
      enabled: Boolean(fleetId),
    },
  );
}

export function useFleetPersonality(fleetId: string | null | undefined) {
  return useAppQuery<FleetPersonalityProfile>(
    fleetQueryKeys.personality(fleetId),
    () =>
      fleetApi.get<FleetPersonalityProfile>(
        `/api/v1/fleets/${encodeURIComponent(fleetId ?? "")}/personality-profile`,
      ),
    {
      enabled: Boolean(fleetId),
    },
  );
}

