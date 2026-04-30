"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  inviteWorkspaceMember,
  listWorkspaceMembers,
  removeWorkspaceMember,
  transferWorkspaceOwnership,
  updateWorkspaceMemberRole,
} from "@/lib/api/workspace-owner";
import type { WorkspaceMember } from "@/lib/schemas/workspace-owner";

export function useWorkspaceMembers(workspaceId: string | null) {
  return useQuery({
    queryKey: ["workspace-owner", workspaceId, "members"],
    queryFn: () => listWorkspaceMembers(workspaceId as string),
    enabled: Boolean(workspaceId),
  });
}

export function useInviteWorkspaceMember(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { user_id: string; role: WorkspaceMember["role"] }) =>
      inviteWorkspaceMember(workspaceId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspace-owner", workspaceId, "members"] });
    },
  });
}

export function useUpdateWorkspaceMemberRole(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: WorkspaceMember["role"] }) =>
      updateWorkspaceMemberRole(workspaceId, userId, { role }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspace-owner", workspaceId, "members"] });
    },
  });
}

export function useRemoveWorkspaceMember(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeWorkspaceMember(workspaceId, userId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["workspace-owner", workspaceId, "members"] });
    },
  });
}

export function useTransferWorkspaceOwnership(workspaceId: string) {
  return useMutation({
    mutationFn: (newOwnerId: string) => transferWorkspaceOwnership(workspaceId, newOwnerId),
  });
}
