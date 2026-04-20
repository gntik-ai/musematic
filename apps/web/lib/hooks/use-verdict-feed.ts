"use client";

import { useMemo } from "react";
import { useAppInfiniteQuery } from "@/lib/hooks/use-api";
import type { GovernanceVerdict } from "@/types/governance";
import { createApiClient } from "@/lib/api";

const governanceApi = createApiClient(
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

function normalizeVerdict(raw: unknown): GovernanceVerdict {
  const item = asRecord(raw);
  return {
    id: asString(item.id),
    offendingAgentFqn: asString(item.target_agent_fqn ?? item.targetAgentFqn, "unknown:agent"),
    verdictType:
      asString(item.verdict_type ?? item.verdictType, "policy_violation") as GovernanceVerdict["verdictType"],
    enforcerAgentFqn: asString(item.judge_agent_fqn ?? item.judgeAgentFqn, "governance:judge"),
    actionTaken:
      (asString(item.recommended_action ?? item.actionTaken, "warn") as GovernanceVerdict["actionTaken"]),
    issuedAt: asString(item.created_at ?? item.issuedAt),
    rationaleExcerpt: asString(item.rationale, ""),
  };
}

export function useVerdictFeed() {
  const query = useAppInfiniteQuery<{ items: GovernanceVerdict[]; next_cursor: string | null }, string | null>(
    ["verdicts"],
    async (cursor) => {
      const suffix = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
      const response = await governanceApi.get<{ items?: unknown[]; next_cursor?: string | null }>(
        `/governance/verdicts${suffix}`,
      );
      return {
        items: (response.items ?? []).map(normalizeVerdict),
        next_cursor: response.next_cursor ?? null,
      };
    },
    {
      initialCursor: null,
      getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    },
  );

  const items = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data?.pages],
  );

  return {
    ...query,
    items,
  };
}
