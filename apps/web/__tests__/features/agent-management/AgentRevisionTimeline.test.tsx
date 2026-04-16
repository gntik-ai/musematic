import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentRevisionTimeline } from "@/components/features/agent-management/AgentRevisionTimeline";
import { renderWithProviders } from "@/test-utils/render";
import { sampleRevisions, seedAgentManagementStores } from "@/__tests__/features/agent-management/test-helpers";

const rollbackMutateAsync = vi.fn();
const toast = vi.fn();

vi.mock("@/lib/hooks/use-toast", () => ({
  useToast: () => ({ toast }),
}));

vi.mock("@/lib/hooks/use-agent-revisions", () => ({
  useAgentRevisions: () => ({
    data: { items: sampleRevisions },
  }),
}));

vi.mock("@/lib/hooks/use-agent-mutations", () => ({
  useRollbackRevision: () => ({
    isPending: false,
    mutateAsync: rollbackMutateAsync,
  }),
}));

describe("AgentRevisionTimeline", () => {
  beforeEach(() => {
    rollbackMutateAsync.mockReset();
    toast.mockReset();
    seedAgentManagementStores();
  });

  it("enables compare for exactly two revisions, disables a third, and rolls back after confirmation", async () => {
    const onSelectForDiff = vi.fn();

    rollbackMutateAsync.mockResolvedValue(undefined);

    renderWithProviders(
      <AgentRevisionTimeline fqn="risk:kyc-monitor" onSelectForDiff={onSelectForDiff} />,
    );

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]!);
    fireEvent.click(checkboxes[1]!);

    expect(screen.getByRole("button", { name: "Compare selected" })).toBeEnabled();
    expect(checkboxes[2]!).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Compare selected" }));
    expect(onSelectForDiff).toHaveBeenCalledWith([1, 2]);

    fireEvent.click(screen.getAllByRole("button", { name: "Rollback" })[0]!);
    expect(await screen.findByText("Rollback revision?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Confirm rollback" }));

    await waitFor(() => {
      expect(rollbackMutateAsync).toHaveBeenCalledWith({
        fqn: "risk:kyc-monitor",
        revisionNumber: 1,
      });
    });
  });
});
