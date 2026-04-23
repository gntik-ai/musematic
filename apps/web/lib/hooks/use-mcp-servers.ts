"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import type { McpServerRegistration } from "@/types/contracts";

const mcpApi = createApiClient(
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

function normalizeServer(raw: unknown): McpServerRegistration {
  const item = asRecord(raw);
  const health = asRecord(item.health);
  const status = asString(health.status, asString(item.status, "unknown"));
  return {
    id: asString(item.server_id ?? item.id),
    name: asString(item.display_name ?? item.name),
    endpoint: asString(item.endpoint_url ?? item.endpoint),
    capabilityCounts: {
      tools: Number(item.tool_count ?? 0),
      resources: 0,
    },
    healthStatus:
      status === "healthy" || status === "degraded"
        ? "healthy"
        : status === "offline" || status === "error"
          ? "unhealthy"
          : "unknown",
    lastHealthCheckAt: asString(health.last_success_at, null as never) || null,
  };
}

export function useMcpServers(agentId: string) {
  const query = useAppQuery<{ items: McpServerRegistration[]; total: number }>(
    ["mcp-servers", agentId],
    async () => {
      const response = await mcpApi.get<{ items?: unknown[]; total?: number }>("/api/v1/mcp/servers");
      return {
        items: (response.items ?? []).map(normalizeServer),
        total: response.total ?? 0,
      };
    },
    {
      enabled: Boolean(agentId),
    },
  );

  return {
    ...query,
    servers: query.data?.items ?? [],
  };
}

export function useMcpServerMutations(agentId: string) {
  const disconnectServer = useAppMutation<void, { serverId: string }>(
    async ({ serverId }) => {
      await mcpApi.delete(`/api/v1/mcp/servers/${encodeURIComponent(serverId)}`);
    },
    {
      invalidateKeys: [["mcp-servers", agentId]],
    },
  );

  return { disconnectServer };
}
