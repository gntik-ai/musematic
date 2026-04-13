import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PendingActions } from "@/components/features/home/PendingActions";
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

describe("PendingActions", () => {
  beforeEach(() => {
    toastSpy.mockReset();
    push.mockReset();
  });

  it("renders pending action cards sorted by urgency", async () => {
    renderWithProviders(<PendingActions isConnected workspaceId="workspace-1" />);

    const headings = await screen.findAllByRole("heading", { level: 3 });
    expect(headings.map((heading) => heading.textContent)).toEqual([
      "Execution failed: runtime-sandbox-healthcheck",
      "Approval required: policy-enforcement-agent",
      "Agent attention requested: trust-escalation-monitor",
    ]);
  });

  it("optimistically removes a card and shows a success toast on approve", async () => {
    const user = userEvent.setup();

    renderWithProviders(<PendingActions isConnected workspaceId="workspace-1" />);

    expect(
      await screen.findByText("Approval required: policy-enforcement-agent"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(
        screen.queryByText("Approval required: policy-enforcement-agent"),
      ).not.toBeInTheDocument();
    });

    expect(toastSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Action completed",
        variant: "success",
      }),
    );
  });

  it("rolls back optimistic removal when the approval endpoint returns 409", async () => {
    const user = userEvent.setup();

    server.use(
      http.post("*/api/v1/workspaces/:workspaceId/approvals/:approvalId/approve", () =>
        HttpResponse.json(
          {
            error: {
              code: "already_resolved",
              message: "Already resolved",
            },
          },
          { status: 409 },
        ),
      ),
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/pending-actions", () =>
        HttpResponse.json(homeFixtures.pendingByWorkspace["workspace-1"]),
      ),
    );

    renderWithProviders(<PendingActions isConnected workspaceId="workspace-1" />);

    expect(
      await screen.findByText("Approval required: policy-enforcement-agent"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(
        screen.getByText("Approval required: policy-enforcement-agent"),
      ).toBeInTheDocument();
    });

    expect(toastSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "This action has already been resolved",
        variant: "destructive",
      }),
    );
  });

  it("shows the all clear empty state when there are no pending actions", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/pending-actions", () =>
        HttpResponse.json({ workspace_id: "workspace-1", items: [], total: 0 }),
      ),
    );

    renderWithProviders(<PendingActions isConnected workspaceId="workspace-1" />);

    expect(await screen.findByText("All clear")).toBeInTheDocument();
    expect(
      screen.getByText("All clear — no pending actions"),
    ).toBeInTheDocument();
  });

  it("shows a section error when the pending actions API fails", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/pending-actions", () =>
        HttpResponse.json(
          {
            error: {
              code: "pending_actions_unavailable",
              message: "Pending actions unavailable",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<PendingActions isConnected workspaceId="workspace-1" />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getAllByText("Pending actions unavailable")).toHaveLength(2);
  });
});
