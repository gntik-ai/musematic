import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExperimentLauncherForm } from "@/components/features/discovery/ExperimentLauncherForm";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerMocks.push }),
}));

describe("ExperimentLauncherForm", () => {
  beforeEach(() => {
    routerMocks.push.mockReset();
  });

  it("submits the existing experiment endpoint contract and routes to experiments", async () => {
    const user = userEvent.setup();
    let capturedBody: unknown;
    server.use(
      http.post("*/api/v1/discovery/hypotheses/hypothesis-1/experiment", async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          experiment_id: "experiment-1",
          hypothesis_id: "hypothesis-1",
          session_id: "session-1",
          plan: {},
          governance_status: "approved",
          governance_violations: [],
          execution_status: "running",
          sandbox_execution_id: "exec-1",
          results: null,
          designed_by_agent_fqn: "scientist:planner",
          created_at: "2026-05-01T10:00:00.000Z",
          updated_at: "2026-05-01T10:00:00.000Z",
        });
      }),
    );

    renderWithProviders(
      <ExperimentLauncherForm hypothesisId="hypothesis-1" workspaceId="workspace-1" />,
    );

    await user.type(screen.getByLabelText("Experiment notes"), "Compare baselines");
    await user.click(screen.getByRole("button", { name: "Launch Experiment" }));

    await waitFor(() => {
      expect(capturedBody).toEqual({ workspace_id: "workspace-1" });
      expect(routerMocks.push).toHaveBeenCalledWith("/discovery/session-1/experiments");
    });
  });
});
