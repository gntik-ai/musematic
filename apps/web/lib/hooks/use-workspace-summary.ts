"use client";

import { useQuery } from "@tanstack/react-query";
import { getWorkspaceSummary } from "@/lib/api/workspace-owner";

export function useWorkspaceSummary(workspaceId: string | null) {
  return useQuery({
    queryKey: ["workspace-owner", workspaceId, "summary"],
    queryFn: () => getWorkspaceSummary(workspaceId as string),
    enabled: Boolean(workspaceId),
    staleTime: 30_000,
  });
}
