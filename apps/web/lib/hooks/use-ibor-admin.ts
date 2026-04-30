"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createIBORConnector,
  getIBORSyncHistory,
  listIBORConnectors,
  syncIBORNow,
  testIBORConnection,
} from "@/lib/api/workspace-owner";
import type { IBORConnectorCreate } from "@/lib/schemas/workspace-owner";

export function useIBORConnectors() {
  return useQuery({
    queryKey: ["admin", "ibor", "connectors"],
    queryFn: listIBORConnectors,
    staleTime: 30_000,
  });
}

export function useIBORSyncHistory(connectorId: string | null, cursor?: string | null) {
  return useQuery({
    queryKey: ["admin", "ibor", connectorId, "sync-history", cursor ?? null],
    queryFn: () => getIBORSyncHistory(connectorId as string, cursor),
    enabled: Boolean(connectorId),
  });
}

export function useIBORTestConnection() {
  return useMutation({
    mutationFn: testIBORConnection,
  });
}

export function useCreateIBORConnector() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: IBORConnectorCreate) => createIBORConnector(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["admin", "ibor", "connectors"],
      });
    },
  });
}

export function useIBORSyncNow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: syncIBORNow,
    onSuccess: async (_result, connectorId) => {
      await queryClient.invalidateQueries({
        queryKey: ["admin", "ibor", connectorId, "sync-history"],
      });
    },
  });
}
