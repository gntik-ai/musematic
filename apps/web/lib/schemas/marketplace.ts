"use client";

import { z } from "zod";
import {
  CERTIFICATION_STATUSES,
  COST_TIERS,
  DEFAULT_MARKETPLACE_SEARCH_PARAMS,
  MATURITY_LEVELS,
  SORT_OPTIONS,
  TRUST_TIERS,
  type MarketplaceSearchParams,
} from "@/lib/types/marketplace";

const emptyStringToUndefined = (value: string | undefined) =>
  value && value.length > 0 ? value : undefined;

export const ReviewSubmissionSchema = z.object({
  rating: z.number().int().min(1).max(5),
  text: z.string().trim().max(2000).optional().transform(emptyStringToUndefined),
});

export const InvocationSchema = z.object({
  workspaceId: z.string().min(1, "Please select a workspace"),
  taskBrief: z.string().trim().max(500).optional().transform(emptyStringToUndefined),
});

export const SearchParamsSchema = z.object({
  q: z.string().default(""),
  capabilities: z.array(z.string()).default([]),
  maturityLevels: z.array(z.enum(MATURITY_LEVELS)).default([]),
  trustTiers: z.array(z.enum(TRUST_TIERS)).default([]),
  certificationStatuses: z.array(z.enum(CERTIFICATION_STATUSES)).default([]),
  costTiers: z.array(z.enum(COST_TIERS)).default([]),
  tags: z.array(z.string()).default([]),
  sortBy: z.enum(SORT_OPTIONS).default("relevance"),
});

type SearchParamSource = URLSearchParams | { toString: () => string };

function readCsv(values: string | null): string[] {
  if (!values) {
    return [];
  }

  return values
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function parseMarketplaceSearchParams(
  source: SearchParamSource,
): MarketplaceSearchParams {
  const searchParams =
    source instanceof URLSearchParams ? source : new URLSearchParams(source.toString());
  const parsed = SearchParamsSchema.parse({
    q: searchParams.get("q") ?? "",
    capabilities: readCsv(searchParams.get("capabilities")),
    maturityLevels: readCsv(searchParams.get("maturityLevels")),
    trustTiers: readCsv(searchParams.get("trustTiers")),
    certificationStatuses: readCsv(searchParams.get("certificationStatuses")),
    costTiers: readCsv(searchParams.get("costTiers")),
    tags: readCsv(searchParams.get("tags")),
    sortBy: searchParams.get("sortBy") ?? DEFAULT_MARKETPLACE_SEARCH_PARAMS.sortBy,
  });

  const page = Number(searchParams.get("page") ?? DEFAULT_MARKETPLACE_SEARCH_PARAMS.page);
  const pageSize = Number(
    searchParams.get("pageSize") ?? DEFAULT_MARKETPLACE_SEARCH_PARAMS.pageSize,
  );

  return {
    ...DEFAULT_MARKETPLACE_SEARCH_PARAMS,
    ...parsed,
    page: Number.isFinite(page) && page > 0 ? page : DEFAULT_MARKETPLACE_SEARCH_PARAMS.page,
    pageSize:
      Number.isFinite(pageSize) && pageSize > 0
        ? pageSize
        : DEFAULT_MARKETPLACE_SEARCH_PARAMS.pageSize,
  };
}

export function serializeMarketplaceSearchParams(
  params: Partial<MarketplaceSearchParams>,
): URLSearchParams {
  const merged: MarketplaceSearchParams = {
    ...DEFAULT_MARKETPLACE_SEARCH_PARAMS,
    ...params,
  };
  const searchParams = new URLSearchParams();

  if (merged.q) {
    searchParams.set("q", merged.q);
  }

  if (merged.capabilities.length > 0) {
    searchParams.set("capabilities", merged.capabilities.join(","));
  }

  if (merged.maturityLevels.length > 0) {
    searchParams.set("maturityLevels", merged.maturityLevels.join(","));
  }

  if (merged.trustTiers.length > 0) {
    searchParams.set("trustTiers", merged.trustTiers.join(","));
  }

  if (merged.certificationStatuses.length > 0) {
    searchParams.set(
      "certificationStatuses",
      merged.certificationStatuses.join(","),
    );
  }

  if (merged.costTiers.length > 0) {
    searchParams.set("costTiers", merged.costTiers.join(","));
  }

  if (merged.tags.length > 0) {
    searchParams.set("tags", merged.tags.join(","));
  }

  if (merged.sortBy !== DEFAULT_MARKETPLACE_SEARCH_PARAMS.sortBy) {
    searchParams.set("sortBy", merged.sortBy);
  }

  return searchParams;
}

export type ReviewSubmissionValues = z.infer<typeof ReviewSubmissionSchema>;
export type InvocationValues = z.infer<typeof InvocationSchema>;
