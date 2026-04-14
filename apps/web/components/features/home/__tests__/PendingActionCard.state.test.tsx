import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PendingActionCard } from "@/components/features/home/PendingActionCard";
import type { PendingAction } from "@/lib/types/home";

const push = vi.fn();
const useApproveMutationMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}));

vi.mock("@/lib/hooks/use-home-data", () => ({
  useApproveMutation: useApproveMutationMock,
}));

describe("PendingActionCard busy state", () => {
  beforeEach(() => {
    push.mockReset();
    useApproveMutationMock.mockReset();
  });

  it("disables non-navigation actions and shows a spinner while a mutation is pending", () => {
    useApproveMutationMock.mockReturnValue({
      isPending: true,
      mutateAsync: vi.fn(),
    });

    const action: PendingAction = {
      id: "action-1",
      type: "approval",
      title: "Approval required",
      description: "An operator decision is required.",
      urgency: "medium",
      created_at: "2026-04-13T12:00:00.000Z",
      href: "/executions/execution-1",
      actions: [
        {
          id: "open-details",
          label: "View Details",
          variant: "ghost",
          action: "navigate",
        },
        {
          id: "approve",
          label: "Approve",
          variant: "default",
          action: "approve",
          endpoint: "/api/v1/workspaces/workspace-1/approvals/approval-1/approve",
          method: "POST",
        },
      ],
    };

    const { container } = render(
      <PendingActionCard action={action} workspaceId="workspace-1" />,
    );

    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "View Details" })).toBeEnabled();
    expect(container.querySelector(".animate-spin")).not.toBeNull();
  });
});
