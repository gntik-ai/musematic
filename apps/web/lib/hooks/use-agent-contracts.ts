"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import type { AgentContract } from "@/types/contracts";

const trustApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function normalizeContract(raw: unknown): AgentContract {
  const item = asRecord(raw);
  const isArchived = Boolean(item.is_archived);
  return {
    id: asString(item.id),
    version: String(item.updated_at ?? item.created_at ?? "1"),
    status: isArchived ? "superseded" : "active",
    publishedAt: asString(item.created_at),
    supersededAt: isArchived ? asString(item.updated_at, null as never) : null,
    signatories: [asString(item.agent_id)].filter(Boolean),
    documentExcerpt: asString(item.task_scope),
  };
}

export function useAgentContracts(agentId: string) {
  const query = useAppQuery<{ items: AgentContract[]; total: number }>(
    ["contracts", agentId],
    async () => {
      const response = await trustApi.get<{ items?: unknown[]; total?: number }>(
        `/api/v1/trust/contracts?agent_id=${encodeURIComponent(agentId)}&include_archived=true`,
      );
      return {
        items: (response.items ?? []).map(normalizeContract),
        total: response.total ?? 0,
      };
    },
    {
      enabled: Boolean(agentId),
    },
  );

  return {
    ...query,
    contracts: query.data?.items ?? [],
  };
}

export function useContractMutations(agentId: string) {
  const archiveContract = useAppMutation<void, { contractId: string }>(
    async ({ contractId }) => {
      await trustApi.delete(`/api/v1/trust/contracts/${encodeURIComponent(contractId)}`);
    },
    {
      invalidateKeys: [["contracts", agentId]],
    },
  );

  return { archiveContract };
}
