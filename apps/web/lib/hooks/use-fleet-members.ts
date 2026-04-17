"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAppQuery } from "@/lib/hooks/use-api";
import { fleetApi, fleetQueryKeys } from "@/lib/hooks/use-fleets";
import type {
  AddFleetMemberInput,
  FleetMember,
  RemoveFleetMemberInput,
  UpdateFleetMemberRoleInput,
} from "@/lib/types/fleet";

interface FleetMembersResponse {
  items: FleetMember[];
}

export function useFleetMembers(fleetId: string | null | undefined) {
  return useAppQuery<FleetMember[]>(
    fleetQueryKeys.members(fleetId),
    async () => {
      const response = await fleetApi.get<FleetMembersResponse>(
        `/api/v1/fleets/${encodeURIComponent(fleetId ?? "")}/members`,
      );
      return response.items;
    },
    {
      enabled: Boolean(fleetId),
    },
  );
}

export function useAddFleetMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fleetId, agentFqn, role }: AddFleetMemberInput) =>
      fleetApi.post<FleetMember>(`/api/v1/fleets/${encodeURIComponent(fleetId)}/members`, {
        agent_fqn: agentFqn,
        role,
      }),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.members(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.detail(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.topology(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.health(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: ["fleet", "list"] }),
      ]);
    },
  });
}

export function useRemoveFleetMember() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fleetId, memberId }: RemoveFleetMemberInput) =>
      fleetApi.delete<void>(
        `/api/v1/fleets/${encodeURIComponent(fleetId)}/members/${encodeURIComponent(memberId)}`,
      ),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.members(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.detail(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.topology(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.health(variables.fleetId) }),
      ]);
    },
  });
}

export function useUpdateMemberRole() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fleetId, memberId, role }: UpdateFleetMemberRoleInput) =>
      fleetApi.put<FleetMember>(
        `/api/v1/fleets/${encodeURIComponent(fleetId)}/members/${encodeURIComponent(memberId)}/role`,
        { role },
      ),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.members(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.topology(variables.fleetId) }),
        queryClient.invalidateQueries({ queryKey: fleetQueryKeys.detail(variables.fleetId) }),
      ]);
    },
  });
}
