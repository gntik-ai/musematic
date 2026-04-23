import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ConversationPage from "@/app/(main)/conversations/[conversationId]/page";
import { renderWithProviders } from "@/test-utils/render";

vi.mock("next/navigation", () => ({
  useParams: () => ({ conversationId: "conversation-1" }),
}));

vi.mock("@/components/features/alerts/per-interaction-mute-toggle", () => ({
  PerInteractionMuteToggle: ({ interactionId }: { interactionId: string }) => (
    <div data-testid="mute-toggle">{interactionId}</div>
  ),
}));

vi.mock("@/components/features/conversations/ConversationView", () => ({
  ConversationView: () => <div data-testid="conversation-view" />,
}));

vi.mock("@/components/features/conversations/goal-scoped-message-filter", () => ({
  GoalScopedMessageFilter: () => <div data-testid="goal-filter" />,
}));

vi.mock("@/components/features/conversations/workspace-goal-header", () => ({
  WorkspaceGoalHeader: () => <div data-testid="goal-header" />,
}));

vi.mock("@/lib/hooks/use-conversation", () => ({
  useConversation: () => ({
    data: {
      branches: [],
      interactions: [
        {
          agent_fqn: "agent:lead",
          goal_id: null,
          id: "interaction-1",
          reasoning_mode: "react",
          self_correction_count: 0,
          state: "completed",
        },
      ],
      title: "Routing issue triage",
      workspace_id: "workspace-1",
    },
    error: null,
    isLoading: false,
  }),
}));

vi.mock("@/lib/hooks/use-goal-lifecycle", () => ({
  useGoalLifecycle: () => ({ activeGoal: null }),
}));

vi.mock("@/lib/hooks/use-conversation-ws", () => ({
  useConversationWs: vi.fn(),
}));

describe("ConversationPage mute toggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("mounts the per-interaction mute toggle in the conversation header", () => {
    renderWithProviders(<ConversationPage />);

    expect(screen.getByText("Routing issue triage")).toBeInTheDocument();
    expect(screen.getByTestId("mute-toggle")).toHaveTextContent("interaction-1");
  });
});
