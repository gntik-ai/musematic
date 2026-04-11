import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { WorkspaceSummary } from "@/components/features/home/WorkspaceSummary";
import type { WorkspaceSummaryResponse } from "@/lib/types/home";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

const workspaceOne: WorkspaceSummaryResponse = {
  workspace_id: "workspace-1",
  active_agents: 12,
  active_agents_change: 3,
  running_executions: 4,
  running_executions_change: 0,
  pending_approvals: 2,
  pending_approvals_change: -1,
  cost_current: 142_50,
  cost_previous: 130_20,
  period_label: "Apr 2026",
};

const workspaceTwo: WorkspaceSummaryResponse = {
  ...workspaceOne,
  workspace_id: "workspace-2",
  active_agents: 7,
  active_agents_change: -2,
  running_executions: 1,
  pending_approvals: 5,
  cost_current: 70_00,
  cost_previous: 81_00,
};

describe("WorkspaceSummary", () => {
  it("renders the four metric cards from the workspace summary response", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", ({ params }) =>
        HttpResponse.json(
          params.workspaceId === "workspace-2" ? workspaceTwo : workspaceOne,
        ),
      ),
    );

    renderWithProviders(
      <WorkspaceSummary isConnected workspaceId="workspace-1" />,
    );

    expect(await screen.findByText("Active Agents")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Running Executions")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Pending Approvals")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Cost (Apr 2026)")).toBeInTheDocument();
    expect(screen.getByText("$142.50")).toBeInTheDocument();
  });

  it("shows a retryable section error when the summary API fails", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", () =>
        HttpResponse.json(
          {
            error: {
              code: "summary_unavailable",
              message: "Summary backend unavailable",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(
      <WorkspaceSummary isConnected workspaceId="workspace-1" />,
    );

    expect(
      await screen.findByText("Workspace summary unavailable"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("renders loading skeletons before data resolves", () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", async () => {
        await new Promise((resolve) => {
          window.setTimeout(resolve, 200);
        });
        return HttpResponse.json(workspaceOne);
      }),
    );

    const { container } = renderWithProviders(
      <WorkspaceSummary isConnected workspaceId="workspace-1" />,
    );

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("refetches when the workspace changes", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", ({ params }) =>
        HttpResponse.json(
          params.workspaceId === "workspace-2" ? workspaceTwo : workspaceOne,
        ),
      ),
    );

    const view = renderWithProviders(
      <WorkspaceSummary isConnected workspaceId="workspace-1" />,
    );

    expect(await screen.findByText("12")).toBeInTheDocument();

    view.rerender(<WorkspaceSummary isConnected workspaceId="workspace-2" />);

    await waitFor(() => {
      expect(screen.getByText("7")).toBeInTheDocument();
      expect(screen.getByText("$70.00")).toBeInTheDocument();
    });
  });
});
