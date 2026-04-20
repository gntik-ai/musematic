"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { DecisionRationale } from "@/types/goal";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface DecisionRationaleRecordResponse {
  id: string;
  goal_id: string;
  message_id: string;
  agent_fqn: string;
  strategy_name: string;
  decision: string;
  score: number | null;
  matched_terms: string[];
  rationale: string;
  error: string | null;
  created_at: string;
}

interface DecisionRationaleMessageListResponse {
  items: DecisionRationaleRecordResponse[];
  total: number;
}

function getRiskSeverity(
  item: DecisionRationaleRecordResponse,
): "low" | "medium" | "high" {
  if (item.error) {
    return "high";
  }

  if (item.decision !== "respond") {
    if (item.score !== null && item.score < 0.25) {
      return "high";
    }

    return "medium";
  }

  return "low";
}

function normalizeDecisionRationale(
  items: DecisionRationaleRecordResponse[],
): DecisionRationale | null {
  if (items.length === 0) {
    return null;
  }

  return {
    toolChoices: items
      .filter((item) => item.decision === "respond")
      .map((item) => ({
        tool: item.strategy_name,
        reason: item.rationale || `Selected by ${item.strategy_name}.`,
      })),
    retrievedMemories: items
      .filter((item) => item.matched_terms.length > 0)
      .map((item) => ({
        memoryId: item.id,
        relevanceScore: item.score ?? 0,
        excerpt: item.matched_terms.join(", "),
      })),
    riskFlags: items
      .filter((item) => item.error !== null || item.decision !== "respond")
      .map((item) => ({
        category: item.strategy_name,
        severity: getRiskSeverity(item),
        note:
          item.error ??
          item.rationale ??
          "This strategy did not produce a direct response recommendation.",
      })),
    policyChecks: items.map((item) => ({
      policyId: item.id,
      policyName: item.strategy_name,
      verdict: item.error
        ? "deny"
        : item.decision === "respond"
          ? "allow"
          : "warn",
    })),
  };
}

export function useMessageDecisionRationale(
  workspaceId: string | null | undefined,
  goalId: string | null | undefined,
  messageId: string | null | undefined,
) {
  const query = useAppQuery<DecisionRationaleMessageListResponse>(
    ["decision-rationale", workspaceId ?? "none", goalId ?? "none", messageId ?? "none"],
    () =>
      api.get<DecisionRationaleMessageListResponse>(
        `/api/v1/workspaces/${workspaceId}/goals/${goalId}/messages/${messageId}/rationale`,
      ),
    {
      enabled: Boolean(workspaceId) && Boolean(goalId) && Boolean(messageId),
      staleTime: 15_000,
    },
  );

  return {
    ...query,
    rationale: normalizeDecisionRationale(query.data?.items ?? []),
    rawItems: query.data?.items ?? [],
  };
}
