import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReasoningTraceViewer } from "@/components/features/workflows/monitor/ReasoningTraceViewer";
import { renderWithProviders } from "@/test-utils/render";
import type { ReasoningTrace } from "@/types/reasoning";

function buildReasoningTrace(totalBranches = 7): ReasoningTrace {
  return {
    executionId: "execution-1",
    stepId: "evaluate_risk",
    treeId: "tree-1",
    rootBranchId: "branch-1",
    totalBranches,
    budgetSummary: {
      mode: "tree_of_thought",
      maxTokens: 4000,
      usedTokens: 820,
      maxRounds: 4,
      usedRounds: 2,
      maxCostUsd: 0.35,
      usedCostUsd: 0.06,
      status: "completed",
    },
    branches: Array.from({ length: totalBranches }, (_, index) => ({
      id: `branch-${index + 1}`,
      parentId: null,
      depth: 0,
      status: index === 0 ? "completed" : "pruned",
      chainOfThought: [
        {
          index: 1,
          thought: `Thought for branch ${index + 1}`,
          confidence: 0.75,
          tokenCost: 50 + index,
        },
      ],
      tokenUsage: {
        inputTokens: 100,
        outputTokens: 20,
        totalTokens: 120,
        estimatedCostUsd: 0.01,
      },
      budgetRemainingAtCompletion: 3000 - index * 50,
      createdAt: new Date("2026-04-13T09:02:00.000Z").toISOString(),
      completedAt: new Date("2026-04-13T09:03:00.000Z").toISOString(),
    })),
  };
}

describe("ReasoningTraceViewer", () => {
  it("shows an empty state when no reasoning trace exists", () => {
    renderWithProviders(<ReasoningTraceViewer reasoningTrace={null} />);

    expect(screen.getByText("No reasoning traces available")).toBeInTheDocument();
  });

  it("paginates branches with the load-more action", () => {
    renderWithProviders(
      <ReasoningTraceViewer reasoningTrace={buildReasoningTrace()} />,
    );

    expect(screen.getByText("branch-1")).toBeInTheDocument();
    expect(screen.queryByText("branch-7")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Load more branches/i }));

    expect(screen.getByText("branch-7")).toBeInTheDocument();
  });
});
