"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { workflowQueryKeys } from "@/lib/hooks/use-workflow-list";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import type { ExecutionCostSummary } from "@/types/execution";

const analyticsApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function normalizeExecutionCostSummary(
  executionId: string,
  response: { items: Array<Record<string, unknown>> },
): ExecutionCostSummary {
  const items = response.items ?? [];
  const totalInputTokens = items.reduce(
    (sum, item) => sum + Number(item.input_tokens ?? 0),
    0,
  );
  const totalOutputTokens = items.reduce(
    (sum, item) => sum + Number(item.output_tokens ?? 0),
    0,
  );
  const totalTokens = items.reduce(
    (sum, item) => sum + Number(item.total_tokens ?? 0),
    0,
  );
  const totalCostUsd = items.reduce(
    (sum, item) => sum + Number(item.cost_usd ?? 0),
    0,
  );

  return {
    executionId,
    totalInputTokens,
    totalOutputTokens,
    totalTokens,
    totalCostUsd,
    lastUpdatedAt: new Date().toISOString(),
    stepBreakdown: items
      .map((item) => ({
        stepId: String(item.step_id ?? item.agent_fqn ?? ""),
        stepName: String(
          item.step_name ?? item.agent_fqn ?? item.model_id ?? "Unknown step",
        ),
        inputTokens: Number(item.input_tokens ?? 0),
        outputTokens: Number(item.output_tokens ?? 0),
        totalTokens: Number(item.total_tokens ?? 0),
        costUsd: Number(item.cost_usd ?? 0),
        percentageOfTotal:
          totalCostUsd > 0
            ? (Number(item.cost_usd ?? 0) / totalCostUsd) * 100
            : 0,
      }))
      .sort((left, right) => right.costUsd - left.costUsd),
  };
}

export function useCostTracker(executionId: string | null | undefined) {
  const totalTokens = useExecutionMonitorStore((state) => state.totalTokens);
  const totalCostUsd = useExecutionMonitorStore((state) => state.totalCostUsd);
  const costBreakdown = useExecutionMonitorStore((state) => state.costBreakdown);
  const setCostBreakdown = useExecutionMonitorStore((state) => state.setCostBreakdown);
  const breakdownQuery = useAppQuery<ExecutionCostSummary>(
    workflowQueryKeys.analyticsUsage(executionId),
    async () =>
      normalizeExecutionCostSummary(
        executionId ?? "",
        await analyticsApi.get(
          `/api/v1/analytics/usage?execution_id=${encodeURIComponent(executionId ?? "")}`,
        ),
      ),
    {
      enabled: false,
    },
  );

  return {
    totalTokens,
    totalCostUsd,
    costBreakdown,
    breakdownQuery,
    expandedBreakdown: async () => {
      if (!executionId) {
        return null;
      }

      const result = await breakdownQuery.refetch();
      if (result.data) {
        setCostBreakdown(result.data.stepBreakdown);
      }
      return result.data ?? null;
    },
  };
}
