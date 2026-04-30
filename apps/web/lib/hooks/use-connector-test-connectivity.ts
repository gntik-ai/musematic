"use client";

import { useMutation } from "@tanstack/react-query";
import { testConnectorConnectivity } from "@/lib/api/workspace-owner";

export function useConnectorTestConnectivity(workspaceId: string, connectorId: string) {
  return useMutation({
    mutationFn: (payload: { config?: Record<string, unknown>; credential_refs?: Record<string, string> }) =>
      testConnectorConnectivity(workspaceId, connectorId, payload),
  });
}
