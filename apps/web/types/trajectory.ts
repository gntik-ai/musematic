export type EfficiencyScore = "high" | "medium" | "low" | "unscored";

export interface TrajectoryStep {
  index: number;
  toolOrAgentFqn: string;
  startedAt: string;
  durationMs: number;
  tokenUsage: { prompt: number; completion: number };
  efficiencyScore: EfficiencyScore;
  summary: string;
}

export interface Checkpoint {
  id: string;
  executionId: string;
  stepIndex: number;
  createdAt: string;
  reason: string;
  isRollbackCandidate: boolean;
}

export interface DebateTurn {
  participantAgentFqn: string;
  participantDisplayName: string;
  participantIsDeleted: boolean;
  position: "support" | "oppose" | "neutral";
  content: string;
  reasoningTraceId: string | null;
  timestamp: string;
}

export interface ReactCycle {
  index: number;
  thought: string;
  action: { tool: string; args: Record<string, unknown> };
  observation: string;
  durationMs: number;
}
