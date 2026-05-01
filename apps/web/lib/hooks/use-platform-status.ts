"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { wsClient } from "@/lib/ws";

export type OverallState =
  | "operational"
  | "degraded"
  | "partial_outage"
  | "full_outage"
  | "maintenance";

export type IncidentSeverity = "info" | "warning" | "high" | "critical";

export interface MyMaintenanceWindow {
  window_id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  blocks_writes: boolean;
  components_affected: string[];
  affects_my_features: string[];
}

export interface MyPlatformIncident {
  id: string;
  title: string;
  severity: IncidentSeverity;
  started_at: string;
  resolved_at: string | null;
  components_affected: string[];
  last_update_at: string;
  last_update_summary: string;
  affects_my_features: string[];
}

export interface MyPlatformStatus {
  overall_state: OverallState;
  active_maintenance: MyMaintenanceWindow | null;
  active_incidents: MyPlatformIncident[];
}

export const platformStatusQueryKey = ["platform-status", "me"] as const;

const platformStatusApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export function usePlatformStatus() {
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = useState(
    wsClient.connectionState === "connected",
  );
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | undefined>(undefined);

  const query = useQuery({
    queryKey: platformStatusQueryKey,
    queryFn: () =>
      platformStatusApi.get<MyPlatformStatus>("/api/v1/me/platform-status"),
    staleTime: 30_000,
    gcTime: 300_000,
    retry: 1,
    refetchInterval: isConnected ? false : 30_000,
  });

  useEffect(() => wsClient.onConnectionChange(setIsConnected), []);

  useEffect(() => {
    const unsubscribe = wsClient.observe("platform-status", () => {
      setLastUpdatedAt(new Date());
      void queryClient.invalidateQueries({ queryKey: platformStatusQueryKey });
    });
    return () => unsubscribe();
  }, [queryClient]);

  useEffect(() => {
    if (query.dataUpdatedAt > 0) {
      setLastUpdatedAt(new Date(query.dataUpdatedAt));
    }
  }, [query.dataUpdatedAt]);

  return {
    data: query.data,
    isLoading: query.isLoading,
    isConnected,
    lastUpdatedAt,
  };
}
