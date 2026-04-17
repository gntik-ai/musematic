"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useWorkspaceStore } from "@/store/workspace-store";

const discoveryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface DiscoveryHypothesis {
  hypothesis_id: string;
  session_id: string;
  title: string;
  description: string;
  confidence: number;
  elo_score: number | null;
  rank: number | null;
  wins: number;
  losses: number;
  draws: number;
  cluster_id: string | null;
  created_at: string;
}

export interface DiscoveryCluster {
  cluster_id: string;
  session_id: string;
  cluster_label: string;
  centroid_description: string;
  hypothesis_count: number;
  density_metric: number;
  classification: "normal" | "over_explored" | "gap";
  hypothesis_ids: string[];
  computed_at: string;
}

interface HypothesisListResponse {
  items: DiscoveryHypothesis[];
  next_cursor: string | null;
}

interface ClusterListResponse {
  items: DiscoveryCluster[];
  landscape_status: "normal" | "saturated" | "low_data";
}

export function useDiscoveryNetwork(sessionId: string) {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const [snapshot, setSnapshot] = useState<string>("current");

  const enabled = Boolean(sessionId && workspaceId);
  const queryParams = useMemo(() => {
    const params = new URLSearchParams({ workspace_id: workspaceId ?? "" });
    return params.toString();
  }, [workspaceId]);

  const hypothesesQuery = useQuery({
    queryKey: ["discovery", "hypotheses", sessionId, workspaceId, snapshot],
    enabled,
    queryFn: async () => {
      const response = await discoveryApi.get<HypothesisListResponse>(
        `/api/v1/discovery/sessions/${sessionId}/hypotheses?${queryParams}&limit=100`,
      );
      return response.items;
    },
  });

  const clustersQuery = useQuery({
    queryKey: ["discovery", "clusters", sessionId, workspaceId, snapshot],
    enabled,
    queryFn: async () => {
      return discoveryApi.get<ClusterListResponse>(
        `/api/v1/discovery/sessions/${sessionId}/clusters?${queryParams}`,
      );
    },
  });

  const snapshots = useMemo(
    () => [
      { id: "current", label: "Current landscape" },
      ...(clustersQuery.data?.items ?? []).map((cluster) => ({
        id: cluster.computed_at,
        label: new Date(cluster.computed_at).toLocaleString(),
      })),
    ],
    [clustersQuery.data?.items],
  );

  return {
    clusters: clustersQuery.data?.items ?? [],
    hypotheses: hypothesesQuery.data ?? [],
    isLoading: hypothesesQuery.isLoading || clustersQuery.isLoading,
    isError: hypothesesQuery.isError || clustersQuery.isError,
    landscapeStatus: clustersQuery.data?.landscape_status ?? "low_data",
    selectedSnapshot: snapshot,
    setSelectedSnapshot: setSnapshot,
    snapshots,
  };
}
