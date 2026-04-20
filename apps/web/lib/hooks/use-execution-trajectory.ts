"use client";

import { useMemo } from "react";
import { useAppQuery } from "@/lib/hooks/use-api";
import { operatorDashboardApi } from "@/lib/hooks/operator-dashboard-shared";
import type { DebateTurn, EfficiencyScore, ReactCycle, TrajectoryStep } from "@/types/trajectory";

export interface StructuredTraceStep {
  stepNumber: number;
  type: string;
  agentFqn: string | null;
  content: string;
  toolCall: Record<string, unknown> | null;
  qualityScore: number | null;
  tokensUsed: number;
  durationMs: number;
  timestamp: string | null;
}

export interface StructuredReasoningTrace {
  executionId: string;
  technique: string;
  status: string;
  totalTokens: number;
  computeBudgetUsed: number;
  effectiveBudgetScope: string | null;
  computeBudgetExhausted: boolean;
  consensusReached: boolean | null;
  stabilized: boolean | null;
  degradationDetected: boolean | null;
  lastUpdatedAt: string | null;
  steps: StructuredTraceStep[];
}

export const executionExperienceQueryKeys = {
  trajectory: (executionId: string | null | undefined) =>
    ["trajectory", executionId ?? "none"] as const,
  checkpoints: (executionId: string | null | undefined) =>
    ["checkpoints", executionId ?? "none"] as const,
  debate: (executionId: string | null | undefined) =>
    ["debate", executionId ?? "none"] as const,
  reactCycles: (executionId: string | null | undefined) =>
    ["react-cycles", executionId ?? "none"] as const,
};

const DEBATE_TYPES = new Set([
  "position",
  "support",
  "oppose",
  "neutral",
  "critique",
  "rebuttal",
  "synthesis",
]);

const THOUGHT_TYPES = new Set(["thought", "reasoning", "plan", "analysis"]);
const ACTION_TYPES = new Set(["action", "tool_call", "tool-call", "tool"]);
const OBSERVATION_TYPES = new Set(["observation", "result", "response"]);

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value.trim() !== "" ? value : null;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function normalizeStructuredTrace(raw: unknown): StructuredReasoningTrace {
  const value = asRecord(raw);
  const stepsRaw = Array.isArray(value.steps) ? value.steps : [];

  return {
    executionId: asString(value.execution_id ?? value.executionId),
    technique: asString(value.technique, "UNKNOWN"),
    status: asString(value.status, "unknown"),
    totalTokens: asNumber(value.total_tokens ?? value.totalTokens),
    computeBudgetUsed: asNumber(
      value.compute_budget_used ?? value.computeBudgetUsed,
    ),
    effectiveBudgetScope: asNullableString(
      value.effective_budget_scope ?? value.effectiveBudgetScope,
    ),
    computeBudgetExhausted: asBoolean(
      value.compute_budget_exhausted ?? value.computeBudgetExhausted,
    ),
    consensusReached:
      typeof (value.consensus_reached ?? value.consensusReached) === "boolean"
        ? Boolean(value.consensus_reached ?? value.consensusReached)
        : null,
    stabilized:
      typeof (value.stabilized) === "boolean" ? Boolean(value.stabilized) : null,
    degradationDetected:
      typeof (value.degradation_detected ?? value.degradationDetected) === "boolean"
        ? Boolean(value.degradation_detected ?? value.degradationDetected)
        : null,
    lastUpdatedAt: asNullableString(
      value.last_updated_at ?? value.lastUpdatedAt,
    ),
    steps: stepsRaw.map((item, index) => {
      const step = asRecord(item);
      return {
        stepNumber: asNumber(step.step_number ?? step.stepNumber, index + 1),
        type: asString(step.type, "step"),
        agentFqn: asNullableString(step.agent_fqn ?? step.agentFqn),
        content: asString(step.content, "No content recorded."),
        toolCall:
          step.tool_call && typeof step.tool_call === "object"
            ? (step.tool_call as Record<string, unknown>)
            : step.toolCall && typeof step.toolCall === "object"
              ? (step.toolCall as Record<string, unknown>)
              : null,
        qualityScore:
          step.quality_score === null || step.qualityScore === null
            ? null
            : asNumber(step.quality_score ?? step.qualityScore, Number.NaN),
        tokensUsed: asNumber(step.tokens_used ?? step.tokensUsed),
        durationMs: asNumber(step.duration_ms ?? step.durationMs),
        timestamp: asNullableString(step.timestamp),
      };
    }),
  };
}

export async function fetchStructuredReasoningTrace(
  executionId: string,
): Promise<StructuredReasoningTrace> {
  const response = await operatorDashboardApi.get<Record<string, unknown>>(
    `/api/v1/executions/${encodeURIComponent(executionId)}/reasoning-trace?page=1&page_size=500`,
  );
  return normalizeStructuredTrace(response);
}

export function deriveEfficiencyScore(
  qualityScore: number | null,
): EfficiencyScore {
  if (qualityScore === null || !Number.isFinite(qualityScore)) {
    return "unscored";
  }
  if (qualityScore >= 0.8) {
    return "high";
  }
  if (qualityScore >= 0.6) {
    return "medium";
  }
  return "low";
}

export function mapTraceToTrajectory(
  trace: StructuredReasoningTrace,
): TrajectoryStep[] {
  return trace.steps.map((step) => ({
    index: step.stepNumber,
    toolOrAgentFqn: step.agentFqn ?? "Agent no longer exists",
    startedAt: step.timestamp ?? new Date(0).toISOString(),
    durationMs: step.durationMs,
    tokenUsage: {
      prompt: 0,
      completion: step.tokensUsed,
    },
    efficiencyScore: deriveEfficiencyScore(step.qualityScore),
    summary: step.content,
  }));
}

function normalizeDebatePosition(type: string): DebateTurn["position"] {
  if (type === "oppose" || type === "critique" || type === "rebuttal") {
    return "oppose";
  }
  if (type === "support" || type === "position") {
    return "support";
  }
  return "neutral";
}

function formatParticipantDisplayName(agentFqn: string | null): string {
  if (!agentFqn) {
    return "Removed agent";
  }
  const lastSegment = agentFqn.split(":").at(-1) ?? agentFqn;
  return lastSegment.replace(/[-_]/g, " ");
}

export function extractDebateTurns(
  trace: StructuredReasoningTrace,
): DebateTurn[] {
  return trace.steps
    .filter((step) => DEBATE_TYPES.has(step.type.toLowerCase()))
    .map((step) => ({
      participantAgentFqn: step.agentFqn ?? "deleted:agent",
      participantDisplayName: formatParticipantDisplayName(step.agentFqn),
      participantIsDeleted: step.agentFqn === null,
      position: normalizeDebatePosition(step.type.toLowerCase()),
      content: step.content,
      reasoningTraceId: `trace-step-${step.stepNumber}`,
      timestamp: step.timestamp ?? new Date(0).toISOString(),
    }));
}

function createEmptyCycle(index: number): ReactCycle {
  return {
    index,
    thought: "",
    action: {
      tool: "",
      args: {},
    },
    observation: "",
    durationMs: 0,
  };
}

export function extractReactCycles(trace: StructuredReasoningTrace): ReactCycle[] {
  const cycles: ReactCycle[] = [];
  let currentCycle = createEmptyCycle(1);

  const finalizeCurrentCycle = () => {
    if (!currentCycle.thought && !currentCycle.action.tool && !currentCycle.observation) {
      return;
    }
    cycles.push(currentCycle);
    currentCycle = createEmptyCycle(cycles.length + 1);
  };

  trace.steps.forEach((step) => {
    const type = step.type.toLowerCase();

    if (THOUGHT_TYPES.has(type)) {
      if (currentCycle.thought && (currentCycle.action.tool || currentCycle.observation)) {
        finalizeCurrentCycle();
      }
      currentCycle.thought = step.content;
      currentCycle.durationMs += step.durationMs;
      return;
    }

    if (ACTION_TYPES.has(type)) {
      currentCycle.action = {
        tool: asString(step.toolCall?.tool ?? step.toolCall?.name, step.agentFqn ?? "Tool"),
        args:
          step.toolCall && typeof step.toolCall.args === "object" && step.toolCall.args !== null
            ? (step.toolCall.args as Record<string, unknown>)
            : {},
      };
      currentCycle.durationMs += step.durationMs;
      return;
    }

    if (OBSERVATION_TYPES.has(type)) {
      currentCycle.observation = step.content;
      currentCycle.durationMs += step.durationMs;
      finalizeCurrentCycle();
      return;
    }

    if (trace.technique.toUpperCase() === "REACT") {
      if (!currentCycle.thought) {
        currentCycle.thought = step.content;
      } else if (!currentCycle.action.tool) {
        currentCycle.action = { tool: step.agentFqn ?? "Tool", args: step.toolCall ?? {} };
      } else if (!currentCycle.observation) {
        currentCycle.observation = step.content;
        finalizeCurrentCycle();
      }
      currentCycle.durationMs += step.durationMs;
    }
  });

  finalizeCurrentCycle();

  return cycles;
}

export function useExecutionTrajectory(executionId: string | null | undefined) {
  const traceQuery = useAppQuery(
    executionExperienceQueryKeys.trajectory(executionId),
    async () => fetchStructuredReasoningTrace(executionId ?? ""),
    {
      enabled: Boolean(executionId),
      staleTime: Number.POSITIVE_INFINITY,
    },
  );

  const data = useMemo(
    () => (traceQuery.data ? mapTraceToTrajectory(traceQuery.data) : undefined),
    [traceQuery.data],
  );

  return {
    ...traceQuery,
    data,
    trace: traceQuery.data,
  };
}
