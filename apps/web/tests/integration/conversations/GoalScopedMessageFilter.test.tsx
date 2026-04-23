import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GoalScopedMessageFilter } from "@/components/features/conversations/goal-scoped-message-filter";

const { replaceSpy } = vi.hoisted(() => ({
  replaceSpy: vi.fn(),
}));

let searchParams = new URLSearchParams("");

vi.mock("next/navigation", () => ({
  usePathname: () => "/conversations/conversation-1",
  useRouter: () => ({
    replace: replaceSpy,
  }),
  useSearchParams: () => searchParams,
}));

vi.mock("@/lib/hooks/use-goal-lifecycle", () => ({
  useGoalLifecycle: () => ({
    goals: [
      {
        id: "goal-1",
        title: "Q2 Sales Analysis",
      },
    ],
  }),
}));

describe("GoalScopedMessageFilter", () => {
  beforeEach(() => {
    replaceSpy.mockReset();
    searchParams = new URLSearchParams("");
  });

  it("enables the goal-scoped query param", async () => {
    const user = userEvent.setup();

    render(
      <GoalScopedMessageFilter
        activeGoalId="goal-1"
        workspaceId="workspace-1"
      />,
    );

    await user.click(screen.getByRole("switch", { name: /toggle goal-scoped filter/i }));

    expect(replaceSpy).toHaveBeenCalledWith(
      "/conversations/conversation-1?goal-scoped=true",
    );
  });

  it("clears the goal-scoped query param from the dismiss action", async () => {
    const user = userEvent.setup();
    searchParams = new URLSearchParams("goal-scoped=true");

    render(
      <GoalScopedMessageFilter
        activeGoalId="goal-1"
        workspaceId="workspace-1"
      />,
    );

    expect(screen.getByText(/filtered to goal: q2 sales analysis/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /dismiss/i }));

    expect(replaceSpy).toHaveBeenCalledWith("/conversations/conversation-1");
  });
});
