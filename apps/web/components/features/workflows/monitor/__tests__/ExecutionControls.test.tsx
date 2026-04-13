import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ExecutionControls } from "@/components/features/workflows/monitor/ExecutionControls";
import { renderWithProviders } from "@/test-utils/render";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import { useAuthStore } from "@/store/auth-store";
import { server } from "@/vitest.setup";

const toastMock = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  toast: (...args: unknown[]) => toastMock(...args),
}));

function seedOperatorState() {
  useExecutionMonitorStore.getState().reset();
  useExecutionMonitorStore.setState({
    executionId: "execution-1",
    executionStatus: "running",
    selectedStepId: "evaluate_risk",
    stepStatuses: {
      evaluate_risk: "failed",
      finalize_case: "pending",
    },
  });

  useAuthStore.setState({
    accessToken: "token",
    isAuthenticated: true,
    isLoading: false,
    refreshToken: null,
    user: {
      id: "user-1",
      email: "alex@musematic.dev",
      displayName: "Alex Mercer",
      avatarUrl: null,
      roles: ["agent_operator"],
      workspaceId: "workspace-1",
      mfaEnrolled: true,
    },
  });
}

function getConfirmDialog(title: string) {
  const heading = screen.getByRole("heading", { name: title });
  return heading.closest("div.fixed") as HTMLElement;
}

describe("ExecutionControls", () => {
  beforeEach(() => {
    toastMock.mockReset();
    useAuthStore.getState().clearAuth();
    seedOperatorState();
  });

  it("opens confirmation dialogs for execution control actions", async () => {
    renderWithProviders(<ExecutionControls executionId="execution-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByRole("heading", { name: "Pause execution" })).toBeInTheDocument();
    fireEvent.click(within(getConfirmDialog("Pause execution")).getByRole("button", { name: "Cancel" }));

    await act(async () => {
      useExecutionMonitorStore.setState({ executionStatus: "paused" });
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Resume" })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    expect(screen.getByRole("heading", { name: "Resume execution" })).toBeInTheDocument();
    fireEvent.click(within(getConfirmDialog("Resume execution")).getByRole("button", { name: "Cancel" }));

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByRole("heading", { name: "Retry failed step" })).toBeInTheDocument();
    fireEvent.click(within(getConfirmDialog("Retry failed step")).getByRole("button", { name: "Cancel" }));

    await act(async () => {
      useExecutionMonitorStore.setState({
        selectedStepId: "finalize_case",
        stepStatuses: {
          evaluate_risk: "failed",
          finalize_case: "pending",
        },
      });
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Skip" })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(screen.getByRole("heading", { name: "Skip selected step" })).toBeInTheDocument();
  });

  it("confirms the pause action and updates monitor state", async () => {
    renderWithProviders(<ExecutionControls executionId="execution-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    fireEvent.click(screen.getByRole("button", { name: "Pause execution" }));

    await waitFor(() => {
      expect(useExecutionMonitorStore.getState().executionStatus).toBe("paused");
    });
  });

  it("disables operator actions when the user lacks RBAC permissions", () => {
    useAuthStore.setState({
      accessToken: "token",
      isAuthenticated: true,
      isLoading: false,
      refreshToken: null,
      user: {
        id: "user-2",
        email: "viewer@musematic.dev",
        displayName: "Viewer",
        avatarUrl: null,
        roles: ["analytics_viewer"],
        workspaceId: "workspace-1",
        mfaEnrolled: true,
      },
    });

    renderWithProviders(<ExecutionControls executionId="execution-1" />);

    expect(screen.getByRole("button", { name: "Pause" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Inject Variable" })).toBeDisabled();
  });

  it("validates the inject-variable form before submitting", async () => {
    renderWithProviders(<ExecutionControls executionId="execution-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Inject Variable" }));

    expect(
      await screen.findByRole("heading", { name: "Inject variable" }),
    ).toBeInTheDocument();

    const dialog = screen.getByRole("dialog");

    fireEvent.click(
      within(dialog).getByRole("button", { name: /^Inject variable$/i }),
    );

    expect(await screen.findByText("Variable name is required.")).toBeInTheDocument();
    expect(screen.getByText("Value is required.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Variable name"), {
      target: { value: "risk_threshold" },
    });
    fireEvent.change(screen.getByLabelText("Value"), {
      target: { value: "{invalid-json}" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: /^Inject variable$/i }),
    );

    expect(await screen.findByText("Value must be valid JSON.")).toBeInTheDocument();
  });

  it("emits an error toast when an action fails", async () => {
    server.use(
      http.post("*/api/v1/executions/:executionId/pause", () =>
        HttpResponse.json(
          {
            error: {
              code: "EXECUTION_PAUSE_FAILED",
              message: "Pause failed unexpectedly",
            },
          },
          { status: 500 },
        ),
      ),
    );

    renderWithProviders(<ExecutionControls executionId="execution-1" />);

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    fireEvent.click(screen.getByRole("button", { name: "Pause execution" }));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Execution action failed",
          variant: "destructive",
        }),
      );
    });
  });
});
