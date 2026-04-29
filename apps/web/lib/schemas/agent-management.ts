"use client";

import { z } from "zod";
import {
  AGENT_MATURITIES,
  AGENT_ROLE_TYPES,
  AGENT_SORT_FIELDS,
  AGENT_SORT_ORDERS,
  AGENT_STATUSES,
  DEFAULT_AGENT_CATALOG_FILTERS,
  type AgentCatalogFilters,
} from "@/lib/types/agent-management";
import { appendTagLabelFilters, parseTagLabelFilters } from "@/lib/tagging/filter-query";

const emptyStringToNull = (value: unknown): unknown => {
  if (value === "" || value === undefined) {
    return null;
  }

  return value;
};

const SearchParamsSchema = z.object({
  search: z.string().default(DEFAULT_AGENT_CATALOG_FILTERS.search),
  namespace: z.array(z.string()).default([]),
  maturity: z.array(z.enum(AGENT_MATURITIES)).default([]),
  status: z.array(z.enum(AGENT_STATUSES)).default([]),
  sort_by: z
    .enum(AGENT_SORT_FIELDS)
    .default(DEFAULT_AGENT_CATALOG_FILTERS.sort_by),
  sort_order: z
    .enum(AGENT_SORT_ORDERS)
    .default(DEFAULT_AGENT_CATALOG_FILTERS.sort_order),
  limit: z.coerce.number().int().min(1).max(100).default(DEFAULT_AGENT_CATALOG_FILTERS.limit),
});

function readCsv(values: string | null): string[] {
  if (!values) {
    return [];
  }

  return values
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

type SearchParamSource = URLSearchParams | { toString: () => string };

export function parseAgentCatalogFilters(
  source: SearchParamSource,
): AgentCatalogFilters {
  const searchParams =
    source instanceof URLSearchParams ? source : new URLSearchParams(source.toString());
  const parsed = SearchParamsSchema.parse({
    search: searchParams.get("search") ?? DEFAULT_AGENT_CATALOG_FILTERS.search,
    namespace: readCsv(searchParams.get("namespace")),
    maturity: readCsv(searchParams.get("maturity")),
    status: readCsv(searchParams.get("status")),
    sort_by: searchParams.get("sort_by") ?? DEFAULT_AGENT_CATALOG_FILTERS.sort_by,
    sort_order: searchParams.get("sort_order") ?? DEFAULT_AGENT_CATALOG_FILTERS.sort_order,
    limit: searchParams.get("limit") ?? DEFAULT_AGENT_CATALOG_FILTERS.limit,
  });

  return {
    ...DEFAULT_AGENT_CATALOG_FILTERS,
    ...parsed,
    ...parseTagLabelFilters(searchParams),
    cursor: searchParams.get("cursor"),
  };
}

export function serializeAgentCatalogFilters(
  filters: Partial<AgentCatalogFilters>,
): URLSearchParams {
  const merged: AgentCatalogFilters = {
    ...DEFAULT_AGENT_CATALOG_FILTERS,
    ...filters,
  };
  const searchParams = new URLSearchParams();

  if (merged.search) {
    searchParams.set("search", merged.search);
  }

  if (merged.namespace.length > 0) {
    searchParams.set("namespace", merged.namespace.join(","));
  }

  if (merged.maturity.length > 0) {
    searchParams.set("maturity", merged.maturity.join(","));
  }

  if (merged.status.length > 0) {
    searchParams.set("status", merged.status.join(","));
  }

  appendTagLabelFilters(searchParams, {
    tags: merged.tags,
    labels: merged.labels,
  });

  if (merged.sort_by !== DEFAULT_AGENT_CATALOG_FILTERS.sort_by) {
    searchParams.set("sort_by", merged.sort_by);
  }

  if (merged.sort_order !== DEFAULT_AGENT_CATALOG_FILTERS.sort_order) {
    searchParams.set("sort_order", merged.sort_order);
  }

  if (merged.limit !== DEFAULT_AGENT_CATALOG_FILTERS.limit) {
    searchParams.set("limit", String(merged.limit));
  }

  if (merged.cursor) {
    searchParams.set("cursor", merged.cursor);
  }

  return searchParams;
}

export const MetadataFormSchema = z.object({
  namespace: z.string().min(1, "Namespace is required"),
  local_name: z
    .string()
    .min(1, "Local name is required")
    .regex(/^[a-z0-9-]+$/, "Lowercase alphanumeric and hyphens only"),
  name: z.string().min(1).max(100),
  description: z.string().min(1).max(2000),
  purpose: z.string().min(20, "Purpose must be at least 20 characters"),
  approach: z.preprocess(emptyStringToNull, z.string().max(5000).nullable()),
  tags: z.array(z.string()).max(20),
  category: z.string().min(1),
  maturity_level: z.enum(AGENT_MATURITIES),
  role_type: z.enum(AGENT_ROLE_TYPES),
  custom_role: z.preprocess(emptyStringToNull, z.string().max(50).nullable()),
  reasoning_modes: z.array(z.string()).min(1, "At least one reasoning mode required"),
  visibility_patterns: z.array(
    z.object({
      pattern: z.string().min(1),
      description: z.preprocess(emptyStringToNull, z.string().nullable()),
    }),
  ),
});

export type MetadataFormValues = z.infer<typeof MetadataFormSchema>;
