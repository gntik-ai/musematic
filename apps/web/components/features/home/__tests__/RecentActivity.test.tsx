import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { RecentActivity } from "@/components/features/home/RecentActivity";
import type { RecentActivityResponse } from "@/lib/types/home";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

function buildRecentActivity(count = 10): RecentActivityResponse {
  return {
    workspace_id: "workspace-1",
    items: Array.from({ length: count }).map((_, index) => ({
      id: `activity-${index}`,
      type: index % 2 === 0 ? "execution" : "interaction",
      title: `Activity ${index}`,
      status: index % 3 === 0 ? "failed" : "completed",
      timestamp: new Date(
        Date.UTC(2026, 3, 11, 10, 0 - index, 0),
      ).toISOString(),
      href: index % 2 === 0 ? `/executions/${index}` : `/interactions/${index}`,
      metadata:
        index % 2 === 0
          ? { workflow_name: `Workflow ${index}` }
          : { agent_fqn: `ops:agent-${index}` },
    })),
  };
}

describe("RecentActivity", () => {
  it("renders the 10 most recent timeline entries in descending order", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", () =>
        HttpResponse.json(buildRecentActivity(10)),
      ),
    );

    renderWithProviders(<RecentActivity isConnected workspaceId="workspace-1" />);

    const links = await screen.findAllByRole("link");
    expect(links).toHaveLength(10);
    expect(links[0]).toHaveAttribute("href", "/executions/0");
    expect(screen.getByText("Activity 0", { selector: "p" })).toBeInTheDocument();
  });

  it("shows the empty state when no recent activity exists", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", () =>
        HttpResponse.json({ workspace_id: "workspace-1", items: [] }),
      ),
    );

    renderWithProviders(<RecentActivity isConnected workspaceId="workspace-1" />);

    expect(await screen.findByText("No recent activity")).toBeInTheDocument();
    expect(
      screen.getByText(
        "No recent activity — start by creating an agent or running a workflow.",
      ),
    ).toBeInTheDocument();
  });

  it("shows a section error when the activity API fails", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", () =>
        HttpResponse.json(
          {
            error: {
              code: "activity_unavailable",
              message: "Activity stream unavailable",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<RecentActivity isConnected workspaceId="workspace-1" />);

    expect(await screen.findByText("Recent activity unavailable")).toBeInTheDocument();
  });

  it("retries recent activity after an error", async () => {
    let attempt = 0;

    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", () => {
        attempt += 1;

        if (attempt === 1) {
          return HttpResponse.json(
            {
              error: {
                code: "activity_unavailable",
                message: "Activity stream unavailable",
              },
            },
            { status: 500 },
          );
        }

        return HttpResponse.json(buildRecentActivity(2));
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<RecentActivity isConnected workspaceId="workspace-1" />);

    await screen.findByText("Recent activity unavailable");
    await user.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByRole("link", { name: "Activity 0" })).toBeInTheDocument();
    expect(attempt).toBeGreaterThan(1);
  });

  it("renders entries as links to their detail routes", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", () =>
        HttpResponse.json(buildRecentActivity(2)),
      ),
    );

    renderWithProviders(<RecentActivity isConnected workspaceId="workspace-1" />);

    const executionLink = await screen.findByRole("link", {
      name: "Activity 0",
    });

    expect(executionLink).toHaveAttribute("href", "/executions/0");
  });

  it("shows loading placeholders while the activity query is pending", () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", async () => {
        await new Promise((resolve) => {
          window.setTimeout(resolve, 200);
        });
        return HttpResponse.json(buildRecentActivity(2));
      }),
    );

    const { container } = renderWithProviders(
      <RecentActivity isConnected workspaceId="workspace-1" />,
    );

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("maps every supported activity status and omits descriptions when metadata is missing", async () => {
    server.use(
      http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", () =>
        HttpResponse.json({
          workspace_id: "workspace-1",
          items: [
            {
              id: "activity-canceled",
              type: "execution",
              title: "Canceled execution",
              status: "canceled",
              timestamp: "2026-04-11T10:00:00.000Z",
              href: "/executions/canceled",
              metadata: {},
            },
            {
              id: "activity-waiting",
              type: "interaction",
              title: "Waiting interaction",
              status: "waiting",
              timestamp: "2026-04-11T10:01:00.000Z",
              href: "/interactions/waiting",
              metadata: {},
            },
            {
              id: "activity-running",
              type: "execution",
              title: "Running execution",
              status: "running",
              timestamp: "2026-04-11T10:02:00.000Z",
              href: "/executions/running",
              metadata: {},
            },
          ],
        }),
      ),
    );

    renderWithProviders(<RecentActivity isConnected workspaceId="workspace-1" />);

    expect(await screen.findByLabelText("status inactive")).toBeInTheDocument();
    expect(screen.getByLabelText("status pending")).toBeInTheDocument();
    expect(screen.getByLabelText("status running")).toBeInTheDocument();
    expect(screen.queryByText(/^Workflow /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Agent /)).not.toBeInTheDocument();
  });
});
