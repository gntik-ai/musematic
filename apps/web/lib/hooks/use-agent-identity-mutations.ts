"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import type { FqnPattern } from "@/types/fqn";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export interface AgentIdentityMutationPayload {
  namespace: string;
  localName: string;
  purpose: string;
  approach?: string;
  roleType: string;
  visibilityPatterns: FqnPattern[];
}

export interface AgentIdentityMutationResponse {
  id: string;
  fqn: string;
  namespace: string;
  localName: string;
  purpose: string;
  approach: string | null;
  roleType: string;
  visibilityPatterns: FqnPattern[];
}

interface AgentIdentityApiResponse {
  id?: string;
  fqn?: string | null;
  namespace?: string | null;
  local_name?: string | null;
  purpose?: string | null;
  approach?: string | null;
  role_type?: string | null;
  visibility_patterns?: Array<{ pattern: string }>;
}

function normalizeResponse(
  payload: AgentIdentityApiResponse,
  fallback: AgentIdentityMutationPayload,
): AgentIdentityMutationResponse {
  const namespace = payload.namespace ?? fallback.namespace;
  const localName = payload.local_name ?? fallback.localName;

  return {
    id: payload.id ?? payload.fqn ?? `${namespace}:${localName}`,
    fqn: payload.fqn ?? `${namespace}:${localName}`,
    namespace,
    localName,
    purpose: payload.purpose ?? fallback.purpose,
    approach: payload.approach ?? fallback.approach ?? null,
    roleType: payload.role_type ?? fallback.roleType,
    visibilityPatterns:
      payload.visibility_patterns?.map((entry) => entry.pattern) ??
      fallback.visibilityPatterns,
  };
}

function serializePayload(payload: AgentIdentityMutationPayload) {
  return {
    namespace: payload.namespace,
    local_name: payload.localName,
    purpose: payload.purpose,
    approach: payload.approach?.trim() ? payload.approach.trim() : null,
    role_type: payload.roleType,
    visibility_patterns: payload.visibilityPatterns.map((pattern) => ({
      pattern,
      description: null,
    })),
  };
}

export function useAgentIdentityMutations(agentId?: string | null) {
  const queryClient = useQueryClient();

  const invalidate = async (resolvedId: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["agent", resolvedId] }),
      queryClient.invalidateQueries({ queryKey: ["marketplace-agents"] }),
      queryClient.invalidateQueries({ queryKey: ["agent-management", "catalog"] }),
      queryClient.invalidateQueries({
        predicate: (query) =>
          Array.isArray(query.queryKey) &&
          (query.queryKey[0] === "marketplace" || query.queryKey[0] === "agent-management"),
      }),
    ]);
  };

  const createAgent = useMutation({
    mutationFn: async (payload: AgentIdentityMutationPayload) =>
      normalizeResponse(
        await api.post<AgentIdentityApiResponse>(
          "/api/v1/agents",
          serializePayload(payload),
        ),
        payload,
      ),
    onSuccess: async (result) => {
      await invalidate(result.id);
    },
  });

  const updateAgent = useMutation({
    mutationFn: async (payload: AgentIdentityMutationPayload) => {
      if (!agentId) {
        throw new Error("agentId is required to update agent identity");
      }

      return normalizeResponse(
        await api.patch<AgentIdentityApiResponse>(
          `/api/v1/agents/${encodeURIComponent(agentId)}`,
          serializePayload(payload),
        ),
        payload,
      );
    },
    onSuccess: async (result) => {
      await invalidate(result.id);
    },
  });

  return {
    createAgent,
    updateAgent,
  };
}
