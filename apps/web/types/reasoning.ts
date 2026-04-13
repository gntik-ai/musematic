import type { TokenUsage } from "@/types/execution";
import type { ReasoningMode } from "@/types/workflows";

export const REASONING_BRANCH_STATUSES = [
  "active",
  "completed",
  "pruned",
  "failed",
] as const;
export const BUDGET_SUMMARY_STATUSES = [
  "active",
  "exhausted",
  "completed",
] as const;
export const SELF_CORRECTION_FINAL_STATUSES = [
  "converged",
  "budget_exceeded",
  "escalated",
  "running",
] as const;
export const SELF_CORRECTION_ITERATION_STATUSES = [
  "continue",
  "converged",
  "budget_exceeded",
  "escalated",
] as const;

export type ReasoningBranchStatus = (typeof REASONING_BRANCH_STATUSES)[number];
export type BudgetSummaryStatus = (typeof BUDGET_SUMMARY_STATUSES)[number];
export type SelfCorrectionFinalStatus =
  (typeof SELF_CORRECTION_FINAL_STATUSES)[number];
export type SelfCorrectionIterationStatus =
  (typeof SELF_CORRECTION_ITERATION_STATUSES)[number];

export interface ChainOfThoughtStep {
  index: number;
  thought: string;
  confidence: number | null;
  tokenCost: number;
}

export interface ReasoningBranch {
  id: string;
  parentId: string | null;
  depth: number;
  status: ReasoningBranchStatus;
  chainOfThought: ChainOfThoughtStep[];
  tokenUsage: TokenUsage;
  budgetRemainingAtCompletion: number | null;
  createdAt: string;
  completedAt: string | null;
}

export interface BudgetSummary {
  mode: ReasoningMode;
  maxTokens: number;
  usedTokens: number;
  maxRounds: number;
  usedRounds: number;
  maxCostUsd: number;
  usedCostUsd: number;
  status: BudgetSummaryStatus;
}

export interface ReasoningTrace {
  executionId: string;
  stepId: string;
  treeId: string;
  rootBranchId: string;
  branches: ReasoningBranch[];
  totalBranches: number;
  budgetSummary: BudgetSummary;
}

export interface SelfCorrectionIteration {
  iterationNumber: number;
  qualityScore: number;
  delta: number;
  status: SelfCorrectionIterationStatus;
  tokenCost: number;
  durationMs: number;
  thoughts: string | null;
}

export interface SelfCorrectionLoop {
  loopId: string;
  executionId: string;
  stepId: string;
  iterations: SelfCorrectionIteration[];
  finalStatus: SelfCorrectionFinalStatus;
  startedAt: string;
  completedAt: string | null;
  budgetConsumed: {
    tokens: number;
    costUsd: number;
    rounds: number;
  };
}
