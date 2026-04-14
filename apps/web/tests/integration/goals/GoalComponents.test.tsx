import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { GoalFeed } from "@/components/features/goals/GoalFeed";
import { GoalLifecycleIndicator } from "@/components/features/goals/GoalLifecycleIndicator";
import { GoalMessageBubble } from "@/components/features/goals/GoalMessageBubble";
import { GoalSelector } from "@/components/features/goals/GoalSelector";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { renderWithProviders } from "@/test-utils/render";
import { getConversationFixtures } from "@/tests/mocks/handlers";
import { server } from "@/vitest.setup";
import { http, HttpResponse } from "msw";

describe("goal components", () => {
  beforeEach(() => {
    useConversationStore.getState().reset();
  });

  it("renders lifecycle badges and goal messages with attribution", () => {
    render(
      <div>
        <GoalLifecycleIndicator status="active" />
        <GoalLifecycleIndicator status="paused" />
        <GoalLifecycleIndicator status="completed" />
        <GoalLifecycleIndicator status="abandoned" />
        <GoalMessageBubble
          message={{
            id: "goal-message-1",
            goal_id: "goal-1",
            sender_type: "agent",
            sender_id: "finance-ops:analyzer",
            sender_display_name: "Finance Analyzer",
            agent_fqn: "finance-ops:analyzer",
            content: "Follow the board-ready storyline.",
            originating_interaction_id: "interaction-1",
            created_at: "2026-04-12T10:00:00.000Z",
          }}
        />
      </div>,
    );

    expect(screen.getByLabelText("Goal status: active")).toBeInTheDocument();
    expect(screen.getByLabelText("Goal status: paused")).toBeInTheDocument();
    expect(screen.getByLabelText("Goal status: completed")).toBeInTheDocument();
    expect(screen.getByLabelText("Goal status: abandoned")).toBeInTheDocument();
    expect(screen.getByText("finance-ops:analyzer")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view interaction/i })).toHaveAttribute(
      "href",
      "/conversations/interaction-1",
    );
  });

  it("renders user and system goal messages without agent attribution links", () => {
    render(
      <div>
        <GoalMessageBubble
          message={{
            id: "goal-message-user",
            goal_id: "goal-1",
            sender_type: "user",
            sender_id: "user-1",
            sender_display_name: "Alex Mercer",
            agent_fqn: null,
            content: "User guidance",
            originating_interaction_id: null,
            created_at: "2026-04-12T10:00:00.000Z",
          }}
        />
        <GoalMessageBubble
          message={{
            id: "goal-message-system",
            goal_id: "goal-1",
            sender_type: "system",
            sender_id: "system",
            sender_display_name: "System",
            agent_fqn: null,
            content: "System notice",
            originating_interaction_id: null,
            created_at: "2026-04-12T10:00:00.000Z",
          }}
        />
      </div>,
    );

    expect(screen.getByText("User guidance")).toBeInTheDocument();
    expect(screen.getByText("System notice")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /view interaction/i })).not.toBeInTheDocument();
  });

  it("updates the selected goal from the selector", async () => {
    const user = userEvent.setup();
    const goals = getConversationFixtures().workspaceGoals["workspace-1"] ?? [];

    render(
      <GoalSelector
        goals={goals}
        selectedGoalId="goal-1"
      />,
    );

    expect(screen.getByLabelText("Goal status: active")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/select goal/i), "goal-2");

    expect(useConversationStore.getState().selectedGoalId).toBe("goal-2");
  });

  it("disables posting for completed goals and shows the background note when the sheet is closed", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/goals", () =>
        HttpResponse.json({
          items: [
            {
              id: "goal-completed",
              workspace_id: "workspace-1",
              title: "Done goal",
              description: "Already resolved",
              status: "completed",
              created_at: "2026-04-12T10:00:00.000Z",
            },
          ],
        }),
      ),
      http.get("*/api/v1/workspaces/:workspaceId/goals/:goalId/messages", () =>
        HttpResponse.json({
          items: [],
          next_cursor: null,
        }),
      ),
    );

    renderWithProviders(
      <GoalFeed
        initialGoalId="goal-completed"
        workspaceId="workspace-1"
      />,
    );

    const textarea = await screen.findByPlaceholderText("This goal has been completed");
    expect(textarea).toBeDisabled();
    expect(screen.getByRole("button", { name: /^send$/i })).toBeDisabled();
    expect(screen.getByText(/goal panel updates continue in the background/i)).toBeInTheDocument();
  });
});
