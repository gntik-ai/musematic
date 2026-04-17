"use client";

import { useMemo } from "react";
import { useExecutionJournal } from "@/lib/hooks/use-execution-journal";
import type { ExecutionJournalFilters } from "@/lib/hooks/use-execution-journal";
import type { ReasoningTrace, SelfCorrectionLoop } from "@/types/reasoning";
import type { TokenUsage } from "@/types/execution";

function normalizeTokenUsage(
  payload: Record<string, unknown> | undefined,
): TokenUsage {
  return {
    inputTokens: Number(payload?.input_tokens ?? payload?.inputTokens ?? 0),
    outputTokens: Number(payload?.output_tokens ?? payload?.outputTokens ?? 0),
    totalTokens: Number(payload?.total_tokens ?? payload?.totalTokens ?? 0),
    estimatedCostUsd: Number(
      payload?.estimated_cost_usd ?? payload?.estimatedCostUsd ?? 0,
    ),
  };
}

function normalizeReasoningTracePayload(
  payload: Record<string, unknown>,
): ReasoningTrace | null {
  const trace = (payload.reasoning_trace ?? payload.reasoningTrace) as
    | Record<string, unknown>
    | undefined;

  if (!trace) {
    return null;
  }

  const branches = Array.isArray(trace.branches) ? trace.branches : [];

  return {
    executionId: String(trace.execution_id ?? trace.executionId ?? ""),
    stepId: String(trace.step_id ?? trace.stepId ?? ""),
    treeId: String(trace.tree_id ?? trace.treeId ?? ""),
    rootBranchId: String(trace.root_branch_id ?? trace.rootBranchId ?? ""),
    totalBranches: Number(trace.total_branches ?? trace.totalBranches ?? branches.length),
    budgetSummary: {
      mode: String(
        (trace.budget_summary as Record<string, unknown> | undefined)?.mode ?? "direct",
      ) as ReasoningTrace["budgetSummary"]["mode"],
      maxTokens: Number(
        (trace.budget_summary as Record<string, unknown> | undefined)?.max_tokens ?? 0,
      ),
      usedTokens: Number(
        (trace.budget_summary as Record<string, unknown> | undefined)?.used_tokens ?? 0,
      ),
      maxRounds: Number(
        (trace.budget_summary as Record<string, unknown> | undefined)?.max_rounds ?? 0,
      ),
      usedRounds: Number(
        (trace.budget_summary as Record<string, unknown> | undefined)?.used_rounds ?? 0,
      ),
      maxCostUsd: Number(
        (trace.budget_summary as Record<string, unknown> | undefined)?.max_cost_usd ?? 0,
      ),
      usedCostUsd: Number(
        (trace.budget_summary as Record<string, unknown> | undefined)?.used_cost_usd ?? 0,
      ),
      status: String(
        (trace.budget_summary as Record<string, unknown> | undefined)?.status ??
          "active",
      ) as ReasoningTrace["budgetSummary"]["status"],
    },
    branches: branches.map((branch) => {
      const value = branch as Record<string, unknown>;
      const chain = Array.isArray(value.chain_of_thought)
        ? (value.chain_of_thought as Record<string, unknown>[])
        : Array.isArray(value.chainOfThought)
          ? (value.chainOfThought as Record<string, unknown>[])
          : [];

      return {
        id: String(value.id ?? ""),
        parentId:
          value.parent_id === null || value.parentId === null
            ? null
            : String(value.parent_id ?? value.parentId ?? ""),
        depth: Number(value.depth ?? 0),
        status: String(value.status ?? "completed") as ReasoningTrace["branches"][number]["status"],
        chainOfThought: chain.map((step, index) => ({
          index: Number(step.index ?? index),
          thought: String(step.thought ?? ""),
          confidence:
            step.confidence === null || step.confidence === undefined
              ? null
              : Number(step.confidence),
          tokenCost: Number(step.token_cost ?? step.tokenCost ?? 0),
        })),
        tokenUsage: normalizeTokenUsage(
          (value.token_usage ?? value.tokenUsage) as Record<string, unknown> | undefined,
        ),
        budgetRemainingAtCompletion:
          value.budget_remaining_at_completion === null ||
          value.budgetRemainingAtCompletion === null
            ? null
            : Number(
                value.budget_remaining_at_completion ??
                  value.budgetRemainingAtCompletion ??
                  0,
              ),
        createdAt: String(value.created_at ?? value.createdAt ?? ""),
        completedAt:
          value.completed_at === null || value.completedAt === null
            ? null
            : String(value.completed_at ?? value.completedAt ?? ""),
      };
    }),
  };
}

function normalizeSelfCorrectionPayload(
  payload: Record<string, unknown>,
): SelfCorrectionLoop | null {
  const loop = (payload.self_correction_loop ?? payload.selfCorrectionLoop) as
    | Record<string, unknown>
    | undefined;

  if (!loop) {
    return null;
  }

  const iterations = Array.isArray(loop.iterations) ? loop.iterations : [];

  return {
    loopId: String(loop.loop_id ?? loop.loopId ?? ""),
    executionId: String(loop.execution_id ?? loop.executionId ?? ""),
    stepId: String(loop.step_id ?? loop.stepId ?? ""),
    finalStatus: String(loop.final_status ?? loop.finalStatus ?? "running") as SelfCorrectionLoop["finalStatus"],
    startedAt: String(loop.started_at ?? loop.startedAt ?? ""),
    completedAt:
      loop.completed_at === null || loop.completedAt === null
        ? null
        : String(loop.completed_at ?? loop.completedAt ?? ""),
    budgetConsumed: {
      tokens: Number(
        (loop.budget_consumed as Record<string, unknown> | undefined)?.tokens ?? 0,
      ),
      costUsd: Number(
        (loop.budget_consumed as Record<string, unknown> | undefined)?.cost_usd ??
          0,
      ),
      rounds: Number(
        (loop.budget_consumed as Record<string, unknown> | undefined)?.rounds ?? 0,
      ),
    },
    iterations: iterations.map((iteration, index) => {
      const value = iteration as Record<string, unknown>;

      return {
        iterationNumber: Number(
          value.iteration_number ?? value.iterationNumber ?? index + 1,
        ),
        qualityScore: Number(value.quality_score ?? value.qualityScore ?? 0),
        delta: Number(value.delta ?? 0),
        status: String(value.status ?? "continue") as SelfCorrectionLoop["iterations"][number]["status"],
        tokenCost: Number(value.token_cost ?? value.tokenCost ?? 0),
        durationMs: Number(value.duration_ms ?? value.durationMs ?? 0),
        thoughts:
          value.thoughts === null || value.thoughts === undefined
            ? null
            : String(value.thoughts),
      };
    }),
  };
}

export function useReasoningTrace(
  executionId: string | null | undefined,
  stepId: string | null | undefined,
) {
  const journalFilters: ExecutionJournalFilters = {
    enabled: Boolean(executionId && stepId),
    eventType: "REASONING_TRACE_EMITTED",
    limit: 20,
    ...(stepId !== undefined ? { stepId } : {}),
  };
  const journalQuery = useExecutionJournal(executionId, journalFilters);

  const events = useMemo(
    () => journalQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [journalQuery.data],
  );

  const reasoningTrace = useMemo(() => {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const payload = events[index]?.payload;
      if (!payload) {
        continue;
      }

      const trace = normalizeReasoningTracePayload(payload);
      if (trace) {
        return trace;
      }
    }

    return null;
  }, [events]);

  const selfCorrectionLoop = useMemo(() => {
    for (let index = events.length - 1; index >= 0; index -= 1) {
      const payload = events[index]?.payload;
      if (!payload) {
        continue;
      }

      const loop = normalizeSelfCorrectionPayload(payload);
      if (loop) {
        return loop;
      }
    }

    return null;
  }, [events]);

  return {
    ...journalQuery,
    events,
    reasoningTrace,
    selfCorrectionLoop,
  };
}
