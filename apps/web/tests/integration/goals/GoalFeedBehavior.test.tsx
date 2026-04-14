import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GoalFeed } from "@/components/features/goals/GoalFeed";
import { useConversationStore } from "@/lib/stores/conversation-store";

const {
  mutateAsyncSpy,
  virtualizerState,
  workspaceGoalState,
} = vi.hoisted(() => ({
  mutateAsyncSpy: vi.fn().mockResolvedValue(undefined),
  virtualizerState: {
    items: [
      { index: 0, key: "goal-message-1", start: 0 },
      { index: 99, key: "missing", start: 96 },
    ],
  },
  workspaceGoalState: {
    goals: [
      {
        id: "goal-1",
        workspace_id: "workspace-1",
        title: "Q2 Sales Analysis",
        description: "Focus the regional storyline",
        status: "active",
        created_at: "2026-04-12T10:00:00.000Z",
      },
    ],
    messages: [
      {
        id: "goal-message-1",
        goal_id: "goal-1",
        sender_type: "agent",
        sender_id: "finance-ops:analyzer",
        sender_display_name: "Finance Analyzer",
        agent_fqn: "finance-ops:analyzer",
        content: "Executive-ready summary",
        originating_interaction_id: "interaction-1",
        created_at: "2026-04-12T10:00:00.000Z",
      },
    ],
  },
}));

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: () => ({
    getTotalSize: () => 192,
    getVirtualItems: () => virtualizerState.items,
    measureElement: vi.fn(),
  }),
}));

vi.mock("@/lib/hooks/use-workspace-goals", () => ({
  canPostToGoal: (goal: { status: string } | null | undefined) =>
    goal ? goal.status !== "completed" && goal.status !== "abandoned" : false,
  getSelectedGoal: (
    goals: Array<{ id: string }>,
    goalId: string | null | undefined,
  ) => goals.find((goal) => goal.id === goalId) ?? goals[0] ?? null,
  useGoalMessages: () => ({
    messages: workspaceGoalState.messages,
  }),
  useGoals: () => ({
    data: {
      items: workspaceGoalState.goals,
    },
  }),
  usePostGoalMessage: () => ({
    mutateAsync: mutateAsyncSpy,
  }),
}));

vi.mock("@/components/features/goals/GoalSelector", () => ({
  GoalSelector: ({ selectedGoalId }: { selectedGoalId: string | null }) => (
    <div>Goal selector {selectedGoalId}</div>
  ),
}));

vi.mock("@/components/features/goals/GoalMessageBubble", () => ({
  GoalMessageBubble: ({ message }: { message: { id: string; content: string } }) => (
    <div>
      bubble {message.id} {message.content}
    </div>
  ),
}));

describe("GoalFeed behavior", () => {
  beforeEach(() => {
    mutateAsyncSpy.mockClear();
    useConversationStore.getState().reset();
    virtualizerState.items = [
      { index: 0, key: "goal-message-1", start: 0 },
      { index: 99, key: "missing", start: 96 },
    ];
  });

  it("renders goal messages, trims outbound content, and clears the composer", async () => {
    const user = userEvent.setup();
    useConversationStore.setState({
      ...useConversationStore.getState(),
      goalPanelOpen: true,
    });

    render(
      <GoalFeed
        initialGoalId="goal-1"
        workspaceId="workspace-1"
      />,
    );

    expect(screen.getByText("Goal selector goal-1")).toBeInTheDocument();
    expect(screen.getByText(/bubble goal-message-1 executive-ready summary/i)).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/add guidance to this goal/i);
    await user.type(textarea, "  Tighten the APAC narrative  ");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      expect(mutateAsyncSpy).toHaveBeenCalledWith({
        content: "Tighten the APAC narrative",
        goalId: "goal-1",
        workspaceId: "workspace-1",
      });
    });
    expect(textarea).toHaveValue("");
    expect(
      screen.queryByText(/goal panel updates continue in the background/i),
    ).not.toBeInTheDocument();
  });
});
