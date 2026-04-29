"use client";

import { createApiClient } from "@/lib/api";
import { useAppInfiniteQuery, useAppQuery } from "@/lib/hooks/use-api";
import type {
  AgentCatalogEntry,
  AgentCatalogFilters,
  AgentDetail,
} from "@/lib/types/agent-management";
import { DEFAULT_AGENT_CATALOG_FILTERS } from "@/lib/types/agent-management";
import { appendTagLabelFilters } from "@/lib/tagging/filter-query";
import { useWorkspaceStore } from "@/store/workspace-store";
import type { CursorPaginatedResponse } from "@/types/api";

const registryApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface AgentCatalogPageResponse {
  items: AgentCatalogEntry[];
  next_cursor: string | null;
  total: number;
}

function normalizeCatalogPage(
  payload: AgentCatalogPageResponse,
): CursorPaginatedResponse<AgentCatalogEntry> {
  return {
    items: payload.items,
    nextCursor: payload.next_cursor,
    prevCursor: null,
    total: payload.total,
  };
}

export const agentManagementQueryKeys = {
  catalog: (
    workspaceId: string | null | undefined,
    filters: AgentCatalogFilters,
  ) => ["agent-management", "catalog", workspaceId ?? "none", filters] as const,
  detail: (workspaceId: string | null | undefined, fqn: string) =>
    ["agent-management", "detail", workspaceId ?? "none", fqn] as const,
  health: (fqn: string) => ["agent-management", "health", fqn] as const,
  revisions: (workspaceId: string | null | undefined, fqn: string) =>
    ["agent-management", "revisions", workspaceId ?? "none", fqn] as const,
  revisionDiff: (fqn: string, base: number | null, compare: number | null) =>
    ["agent-management", "revisions", "diff", fqn, base, compare] as const,
  policies: (workspaceId: string | null | undefined, fqn: string) =>
    ["agent-management", "policies", workspaceId ?? "none", fqn] as const,
  namespaces: (workspaceId: string | null | undefined) =>
    ["agent-management", "namespaces", workspaceId ?? "none"] as const,
  blueprint: (workspaceId: string | null | undefined) =>
    ["agent-management", "composition", workspaceId ?? "none"] as const,
};

function appendMultiValue(
  searchParams: URLSearchParams,
  key: string,
  values: string[],
): void {
  if (values.length === 0) {
    return;
  }

  searchParams.set(key, values.join(","));
}

function buildCatalogPath(
  workspaceId: string,
  filters: AgentCatalogFilters,
  cursor: string | null,
): string {
  const searchParams = new URLSearchParams({
    workspace_id: workspaceId,
    limit: String(filters.limit),
    sort_by: filters.sort_by,
    sort_order: filters.sort_order,
  });

  if (filters.search) {
    searchParams.set("search", filters.search);
  }

  appendMultiValue(searchParams, "namespace", filters.namespace);
  appendMultiValue(searchParams, "maturity", filters.maturity);
  appendMultiValue(searchParams, "status", filters.status);
  appendTagLabelFilters(searchParams, {
    tags: filters.tags,
    labels: filters.labels,
  });

  if (cursor) {
    searchParams.set("cursor", cursor);
  }

  return `/api/v1/registry/agents?${searchParams.toString()}`;
}

export interface UseAgentsOptions {
  enabled?: boolean;
  workspaceId?: string | null;
}

export function useAgents(
  filters: Partial<AgentCatalogFilters> = {},
  options: UseAgentsOptions = {},
) {
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const workspaceId = options.workspaceId ?? currentWorkspaceId;
  const resolvedFilters: AgentCatalogFilters = {
    ...DEFAULT_AGENT_CATALOG_FILTERS,
    ...filters,
  };
  const enabled = (options.enabled ?? true) && Boolean(workspaceId);

  const query = useAppInfiniteQuery<
    CursorPaginatedResponse<AgentCatalogEntry>,
    string | null
  >(
    agentManagementQueryKeys.catalog(workspaceId, resolvedFilters),
    async (cursor) =>
      normalizeCatalogPage(
        await registryApi.get<AgentCatalogPageResponse>(
          buildCatalogPath(workspaceId ?? "", resolvedFilters, cursor ?? null),
        ),
      ),
    {
      enabled,
      initialCursor: resolvedFilters.cursor,
      getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    },
  );

  return {
    ...query,
    agents: query.data?.pages.flatMap((page) => page.items) ?? [],
    total: query.data?.pages[0]?.total ?? 0,
    workspaceId,
  };
}

export interface UseAgentOptions {
  enabled?: boolean;
  workspaceId?: string | null;
}

export function useAgent(
  fqn: string | null | undefined,
  options: UseAgentOptions = {},
) {
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const workspaceId = options.workspaceId ?? currentWorkspaceId;

  return useAppQuery<AgentDetail>(
    agentManagementQueryKeys.detail(workspaceId, fqn ?? ""),
    () =>
      registryApi.get<AgentDetail>(
        `/api/v1/registry/agents/${encodeURIComponent(fqn ?? "")}`,
      ),
    {
      enabled: (options.enabled ?? true) && Boolean(fqn),
    },
  );
}
