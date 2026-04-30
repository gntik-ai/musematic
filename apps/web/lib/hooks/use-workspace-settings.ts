"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getWorkspaceSettings,
  updateWorkspaceSettings,
} from "@/lib/api/workspace-owner";
import type { WorkspaceSettings } from "@/lib/schemas/workspace-owner";

export function useWorkspaceSettings(workspaceId: string | null) {
  return useQuery({
    queryKey: ["workspace-owner", workspaceId, "settings"],
    queryFn: () => getWorkspaceSettings(workspaceId as string),
    enabled: Boolean(workspaceId),
  });
}

export function useWorkspaceSettingsMutation(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      payload: Partial<
        Pick<WorkspaceSettings, "cost_budget" | "quota_config" | "dlp_rules" | "residency_config">
      >,
    ) => updateWorkspaceSettings(workspaceId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspace-owner", workspaceId, "settings"] });
      await queryClient.invalidateQueries({ queryKey: ["workspace-owner", workspaceId, "summary"] });
    },
  });
}
