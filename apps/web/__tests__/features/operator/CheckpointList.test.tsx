import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CheckpointList } from "@/components/features/execution/checkpoint-list";
import { renderWithProviders } from "@/test-utils/render";
import { useAuthStore } from "@/store/auth-store";

const mutateAsync = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/hooks/use-execution-checkpoints", () => ({
  useExecutionCheckpoints: () => ({
    data: [
      {
        id: "execution-1-checkpoint-2",
        executionId: "execution-1",
        stepIndex: 2,
        createdAt: "2026-04-13T09:22:00.000Z",
        reason: "Captured by named-step checkpoint policy.",
        isRollbackCandidate: true,
      },
    ],
    isLoading: false,
  }),
  useCheckpointRollback: () => ({
    isPending: false,
    mutateAsync,
  }),
}));

describe("CheckpointList", () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "alex@musematic.dev",
        displayName: "Alex",
        avatarUrl: null,
        mfaEnrolled: true,
        roles: ["workspace_admin"],
        workspaceId: "workspace-1",
      },
    } as never);
  });

  it("requires typed confirmation before firing rollback", async () => {
    const user = userEvent.setup();

    renderWithProviders(<CheckpointList executionId="execution-1" />);

    await user.click(screen.getByRole("button", { name: /roll back/i }));

    const dialog = screen.getByRole("alertdialog");
    const confirmButton = within(dialog).getByRole("button", { name: /^roll back$/i });
    expect(confirmButton).toBeDisabled();

    await user.type(
      screen.getByPlaceholderText("execution-1-checkpoint-2"),
      "execution-1-checkpoint-2",
    );
    expect(confirmButton).toBeEnabled();

    await user.click(confirmButton);

    expect(mutateAsync).toHaveBeenCalledWith({ checkpointNumber: 2 });
  });
});
