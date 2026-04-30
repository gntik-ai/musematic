"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  approveChallenge,
  consumeChallenge,
  createChallenge,
  getChallenge,
} from "@/lib/api/workspace-owner";

export function useChallenge(challengeId: string | null, options: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: ["2pa", challengeId],
    queryFn: () => getChallenge(challengeId as string),
    enabled: Boolean(challengeId),
    refetchInterval: options.poll ? 2_000 : false,
  });
}

export function useCreateChallenge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createChallenge,
    onSuccess: async (challenge) => {
      await queryClient.invalidateQueries({ queryKey: ["2pa", challenge.id] });
    },
  });
}

export function useApproveChallenge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: approveChallenge,
    onSuccess: async (challenge) => {
      await queryClient.invalidateQueries({ queryKey: ["2pa", challenge.id] });
    },
  });
}

export function useConsumeChallenge() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: consumeChallenge,
    onSuccess: async (challenge) => {
      await queryClient.invalidateQueries({ queryKey: ["2pa", challenge.id] });
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}
