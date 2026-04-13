import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { GoalFeed } from "@/components/features/goals/GoalFeed";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

describe("GoalFeed", () => {
  it("renders goals and posts to the selected goal", async () => {
    const requestSpy = vi.fn();
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/workspaces/:workspaceId/goals/:goalId/messages", async ({ request }) => {
        requestSpy(await request.json());
        return HttpResponse.json({
          id: "goal-message-new",
          goal_id: "goal-1",
          sender_type: "user",
          sender_id: "user-1",
          sender_display_name: "Alex Mercer",
          agent_fqn: null,
          content: "Focus on APAC region",
          originating_interaction_id: null,
          created_at: new Date().toISOString(),
        });
      }),
    );

    renderWithProviders(<GoalFeed workspaceId="workspace-1" />);

    expect(await screen.findByLabelText(/select goal/i)).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/add guidance to this goal/i), {
      target: { value: "Focus on APAC region" },
    });
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => {
      expect(requestSpy).toHaveBeenCalledWith({
        content: "Focus on APAC region",
      });
    });
  });
});
