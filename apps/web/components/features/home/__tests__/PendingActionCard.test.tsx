import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PendingActionCard } from "@/components/features/home/PendingActionCard";
import { homeFixtures } from "@/mocks/handlers/home";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

const { toastSpy } = vi.hoisted(() => ({
  toastSpy: vi.fn(),
}));

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}));

vi.mock("@/lib/hooks/use-toast", () => ({
  toast: toastSpy,
  useToast: () => ({ toast: toastSpy }),
}));

describe("PendingActionCard", () => {
  beforeEach(() => {
    push.mockReset();
    toastSpy.mockReset();
  });

  it("navigates to the action href for navigate-only actions", async () => {
    const user = userEvent.setup();
    const pendingWorkspace = homeFixtures.pendingByWorkspace["workspace-1"]!;
    const action = pendingWorkspace.items[0]!;

    renderWithProviders(
      <PendingActionCard action={action} workspaceId="workspace-1" />,
    );

    await user.click(screen.getByRole("button", { name: "View Details" }));

    expect(push).toHaveBeenCalledWith("/executions/execution-failed-1");
  });

  it("shows a permission toast when the mutation returns 403", async () => {
    const user = userEvent.setup();
    const pendingWorkspace = homeFixtures.pendingByWorkspace["workspace-1"]!;
    const action = pendingWorkspace.items[1]!;

    server.use(
      http.post("*/api/v1/workspaces/:workspaceId/approvals/:approvalId/reject", () =>
        HttpResponse.json(
          {
            error: {
              code: "forbidden",
              message: "Forbidden",
            },
          },
          { status: 403 },
        ),
      ),
    );

    renderWithProviders(
      <PendingActionCard action={action} workspaceId="workspace-1" />,
    );

    await user.click(screen.getByRole("button", { name: "Reject" }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "You don't have permission to perform this action",
          variant: "destructive",
        }),
      );
    });
  });

  it("shows a generic error toast when the mutation fails unexpectedly", async () => {
    const user = userEvent.setup();
    const pendingWorkspace = homeFixtures.pendingByWorkspace["workspace-1"]!;
    const action = pendingWorkspace.items[1]!;

    server.use(
      http.post("*/api/v1/workspaces/:workspaceId/approvals/:approvalId/reject", () =>
        HttpResponse.json(
          {
            error: {
              code: "server_error",
              message: "Unexpected failure",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(
      <PendingActionCard action={action} workspaceId="workspace-1" />,
    );

    await user.click(screen.getByRole("button", { name: "Reject" }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Unable to update this action",
          description: "Unexpected failure",
          variant: "destructive",
        }),
      );
    });
  });

  it("does nothing when an action is missing endpoint metadata", async () => {
    const user = userEvent.setup();
    const pendingWorkspace = homeFixtures.pendingByWorkspace["workspace-1"]!;
    const action = pendingWorkspace.items[2]!;

    renderWithProviders(
      <PendingActionCard
        action={{
          ...action,
          urgency: "low",
          actions: [
            {
              id: "broken-action",
              label: "Resolve",
              variant: "default",
              action: "approve",
            },
          ],
        }}
        workspaceId="workspace-1"
      />,
    );

    expect(screen.getByLabelText("status Info")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Resolve" }));

    expect(push).not.toHaveBeenCalled();
    expect(toastSpy).not.toHaveBeenCalled();
  });
});
