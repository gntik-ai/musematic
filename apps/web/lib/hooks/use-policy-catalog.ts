"use client";

import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";
import {
  appendTagLabelFilters,
  EMPTY_TAG_LABEL_FILTERS,
  type TagLabelFilters,
} from "@/lib/tagging/filter-query";
import { trustWorkbenchApi } from "@/lib/hooks/use-certifications";
import type { PolicySummary } from "@/lib/types/trust-workbench";

interface PolicyCatalogApiResponse {
  items?: Array<Record<string, unknown>>;
  total?: number;
  page?: number;
  pageSize?: number;
  page_size?: number;
}

interface PolicyCatalogResponse {
  items: PolicySummary[];
  total: number;
  page: number;
  pageSize: number;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function normalizePolicySummary(raw: Record<string, unknown>): PolicySummary {
  return {
    id: asString(raw.id),
    name: asString(raw.name),
    description:
      typeof raw.description === "string" ? raw.description : null,
    scopeType:
      raw.scopeType === "global" ||
      raw.scopeType === "deployment" ||
      raw.scopeType === "workspace" ||
      raw.scopeType === "agent" ||
      raw.scopeType === "fleet" ||
      raw.scopeType === "execution"
        ? raw.scopeType
        : raw.scope_type === "global" ||
            raw.scope_type === "deployment" ||
            raw.scope_type === "workspace" ||
            raw.scope_type === "agent" ||
            raw.scope_type === "fleet" ||
            raw.scope_type === "execution"
          ? raw.scope_type
          : "workspace",
    status:
      raw.status === "archived" || raw.status === "suspended"
        ? raw.status
        : "active",
    workspaceId:
      typeof (raw.workspaceId ?? raw.workspace_id) === "string"
        ? ((raw.workspaceId ?? raw.workspace_id) as string)
        : null,
    currentVersionId:
      typeof (raw.currentVersionId ?? raw.current_version_id) === "string"
        ? ((raw.currentVersionId ?? raw.current_version_id) as string)
        : null,
  };
}

export const policyCatalogQueryKeys = {
  root: ["policyCatalog"] as const,
  list: (
    workspaceId: string | null | undefined,
    search: string,
    tagLabelFilters: TagLabelFilters,
  ) => ["policyCatalog", workspaceId ?? "none", search, tagLabelFilters] as const,
};

interface PolicyCreateInput {
  workspaceId: string;
  name: string;
  description: string | null;
  labelExpression: string | null;
}

export function usePolicyCatalog(
  workspaceId: string | null | undefined,
  search = "",
  tagLabelFilters: TagLabelFilters = EMPTY_TAG_LABEL_FILTERS,
) {
  const debouncedSearch = useDebouncedValue(search, 300);

  return useAppQuery<PolicyCatalogResponse>(
    policyCatalogQueryKeys.list(workspaceId, debouncedSearch, tagLabelFilters),
    async () => {
      const searchParams = new URLSearchParams({
        workspace_id: workspaceId ?? "",
        status: "active",
        page: "1",
        page_size: "100",
      });

      if (debouncedSearch) {
        searchParams.set("search", debouncedSearch);
      }
      appendTagLabelFilters(searchParams, tagLabelFilters);

      const response = await trustWorkbenchApi.get<PolicyCatalogApiResponse>(
        `/api/v1/policies?${searchParams.toString()}`,
      );

      return {
        items: (response.items ?? []).map(normalizePolicySummary),
        total: response.total ?? 0,
        page: response.page ?? 1,
        pageSize: response.pageSize ?? response.page_size ?? 100,
      };
    },
    {
      enabled: Boolean(workspaceId),
    },
  );
}

export function usePolicyCreate() {
  return useAppMutation(
    (payload: PolicyCreateInput) =>
      trustWorkbenchApi.post("/api/v1/policies", {
        workspace_id: payload.workspaceId,
        name: payload.name,
        description: payload.description,
        scope_type: "workspace",
        rules: {
          label_expression: payload.labelExpression,
        },
        change_summary: "Initial policy",
      }),
    {
      invalidateKeys: [policyCatalogQueryKeys.root],
    },
  );
}
