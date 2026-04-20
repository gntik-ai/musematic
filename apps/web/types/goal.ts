export type GoalState = "open" | "in_progress" | "completed" | "cancelled";

export interface WorkspaceGoal {
  id: string;
  workspaceId: string;
  title: string;
  description: string;
  state: GoalState;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
}

export interface DecisionRationale {
  toolChoices: Array<{ tool: string; reason: string }>;
  retrievedMemories: Array<{
    memoryId: string;
    relevanceScore: number;
    excerpt: string;
  }>;
  riskFlags: Array<{
    category: string;
    severity: "low" | "medium" | "high";
    note: string;
  }>;
  policyChecks: Array<{
    policyId: string;
    policyName: string;
    verdict: "allow" | "deny" | "warn";
  }>;
}
