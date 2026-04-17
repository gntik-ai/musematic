"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import type {
  AgentDetail,
  AgentMetadataUpdateRequest,
  AgentRevision,
  PublicationSummary,
  ValidationResult,
} from "@/lib/types/agent-management";

const registryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface UpdateAgentMetadataVariables {
  fqn: string;
  body: AgentMetadataUpdateRequest;
  lastModified: string;
}

export function useUpdateAgentMetadata() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ body, fqn, lastModified }: UpdateAgentMetadataVariables) =>
      registryApi.put<AgentDetail>(
        `/api/v1/registry/agents/${encodeURIComponent(fqn)}/metadata`,
        body,
        {
          headers: {
            "If-Unmodified-Since": lastModified,
          },
        },
      ),
    onSuccess: async (_data, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agent-management", "catalog"] }),
        queryClient.invalidateQueries({
          predicate: (query) =>
            Array.isArray(query.queryKey) &&
            query.queryKey[0] === "agent-management" &&
            query.queryKey[1] === "detail" &&
            query.queryKey[3] === variables.fqn,
        }),
      ]);
    },
  });
}

export function useValidateAgent() {
  return useMutation({
    mutationFn: (fqn: string) =>
      registryApi.post<ValidationResult>(
        `/api/v1/registry/agents/${encodeURIComponent(fqn)}/validate`,
      ),
  });
}

export function usePublishAgent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (fqn: string) =>
      registryApi.post<PublicationSummary>(
        `/api/v1/registry/agents/${encodeURIComponent(fqn)}/publish`,
      ),
    onSuccess: async (_data, fqn) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agent-management", "catalog"] }),
        queryClient.invalidateQueries({
          predicate: (query) =>
            Array.isArray(query.queryKey) &&
            query.queryKey[0] === "agent-management" &&
            query.queryKey[1] === "detail" &&
            query.queryKey[3] === fqn,
        }),
      ]);
    },
  });
}

export interface RollbackRevisionVariables {
  fqn: string;
  revisionNumber: number;
}

export function useRollbackRevision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fqn, revisionNumber }: RollbackRevisionVariables) =>
      registryApi.post<AgentRevision>(
        `/api/v1/registry/agents/${encodeURIComponent(fqn)}/revisions/${revisionNumber}/rollback`,
      ),
    onSuccess: async (_data, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          predicate: (query) =>
            Array.isArray(query.queryKey) &&
            query.queryKey[0] === "agent-management" &&
            query.queryKey[1] === "revisions" &&
            query.queryKey[3] === variables.fqn,
        }),
        queryClient.invalidateQueries({
          predicate: (query) =>
            Array.isArray(query.queryKey) &&
            query.queryKey[0] === "agent-management" &&
            query.queryKey[1] === "detail" &&
            query.queryKey[3] === variables.fqn,
        }),
      ]);
    },
  });
}
