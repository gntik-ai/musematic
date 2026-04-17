"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type {
  FleetActionResponse,
  FleetDetail,
  FleetHealthProjection,
  FleetListEntry,
  FleetListFilters,
  FleetMember,
  FleetPerformanceProfile,
  FleetTopologyVersion,
  ObserverFindingFilters,
  PerformanceTimeRange,
  StressTestProgress,
} from "@/lib/types/fleet";
import { DEFAULT_FLEET_LIST_FILTERS } from "@/lib/types/fleet";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

const fleetApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface FleetListResponse {
  items: FleetListEntry[];
  total: number;
  page: number;
  size: number;
}

export interface FleetListQueryOptions {
  workspaceId?: string | null;
  enabled?: boolean;
}

export const fleetQueryKeys = {
  root: ["fleet"] as const,
  lists: (
    workspaceId: string | null | undefined,
    filters: FleetListFilters,
  ) => ["fleet", "list", workspaceId ?? "none", filters] as const,
  detail: (fleetId: string | null | undefined) =>
    ["fleet", "detail", fleetId ?? "none"] as const,
  health: (fleetId: string | null | undefined) =>
    ["fleet", "health", fleetId ?? "none"] as const,
  members: (fleetId: string | null | undefined) =>
    ["fleet", "members", fleetId ?? "none"] as const,
  topology: (fleetId: string | null | undefined) =>
    ["fleet", "topology", fleetId ?? "none"] as const,
  performance: (
    fleetId: string | null | undefined,
    range: PerformanceTimeRange,
  ) => ["fleet", "performance", fleetId ?? "none", range] as const,
  governance: (fleetId: string | null | undefined) =>
    ["fleet", "governance", fleetId ?? "none"] as const,
  orchestration: (fleetId: string | null | undefined) =>
    ["fleet", "orchestration", fleetId ?? "none"] as const,
  personality: (fleetId: string | null | undefined) =>
    ["fleet", "personality", fleetId ?? "none"] as const,
  observerFindings: (
    fleetId: string | null | undefined,
    filters: ObserverFindingFilters,
  ) => ["fleet", "observer-findings", fleetId ?? "none", filters] as const,
  stressTestProgress: (runId: string | null | undefined) =>
    ["fleet", "stress-test", runId ?? "none"] as const,
  actions: (fleetId: string | null | undefined) =>
    ["fleet", "actions", fleetId ?? "none"] as const,
};

function appendMulti(searchParams: URLSearchParams, key: string, values: string[]): void {
  if (values.length > 0) {
    searchParams.set(key, values.join(","));
  }
}

function buildFleetListPath(workspaceId: string, filters: FleetListFilters): string {
  const resolved = {
    ...DEFAULT_FLEET_LIST_FILTERS,
    ...filters,
  };
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
    page: String(resolved.page),
    size: String(resolved.size),
    sort_by: resolved.sort_by,
    sort_order: resolved.sort_order,
  });

  if (resolved.search) {
    searchParams.set("search", resolved.search);
  }
  if (resolved.health_min !== null) {
    searchParams.set("health_min", String(resolved.health_min));
  }

  appendMulti(searchParams, "topology_type", resolved.topology_type);
  appendMulti(searchParams, "status", resolved.status);

  return `/api/v1/fleets?${searchParams.toString()}`;
}

function getCurrentWorkspaceId(override?: string | null): string | null {
  if (override !== undefined) {
    return override;
  }

  return (
    useWorkspaceStore.getState().currentWorkspace?.id ??
    useAuthStore.getState().user?.workspaceId ??
    null
  );
}

export function useFleets(
  filters: FleetListFilters,
  options: FleetListQueryOptions = {},
) {
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = options.workspaceId ?? currentWorkspaceId ?? authWorkspaceId;

  return useAppQuery<FleetListResponse>(
    fleetQueryKeys.lists(workspaceId, filters),
    () => fleetApi.get<FleetListResponse>(buildFleetListPath(workspaceId ?? "", filters)),
    {
      enabled: (options.enabled ?? true) && Boolean(workspaceId),
    },
  );
}

export function useFleet(fleetId: string | null | undefined) {
  return useAppQuery<FleetDetail>(
    fleetQueryKeys.detail(fleetId),
    () => fleetApi.get<FleetDetail>(`/api/v1/fleets/${encodeURIComponent(fleetId ?? "")}`),
    {
      enabled: Boolean(fleetId),
    },
  );
}

export { fleetApi, getCurrentWorkspaceId };
export type {
  FleetActionResponse,
  FleetHealthProjection,
  FleetMember,
  FleetPerformanceProfile,
  FleetTopologyVersion,
  StressTestProgress,
};

