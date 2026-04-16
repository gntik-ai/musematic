import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FleetMemberPanel } from "@/components/features/fleet/FleetMemberPanel";
import { renderWithProviders } from "@/test-utils/render";
import { ApiError } from "@/types/api";
import {
  sampleMembers,
  seedFleetStores,
} from "@/__tests__/features/fleet/test-helpers";

const removeMemberMutation = {
  error: null as ApiError | null,
  isPending: false,
  mutateAsync: vi.fn().mockResolvedValue(undefined),
  reset: vi.fn(),
};

vi.mock("@/lib/hooks/use-fleet-members", () => ({
  useFleetMembers: () => ({
    data: sampleMembers,
  }),
  useRemoveFleetMember: () => removeMemberMutation,
  useAddFleetMember: () => ({
    isPending: false,
    mutateAsync: vi.fn().mockResolvedValue(undefined),
  }),
}));

vi.mock("@/lib/hooks/use-agents", () => ({
  useAgents: () => ({
    agents: [
      {
        fqn: "risk:new-worker",
        name: "New Worker",
      },
    ],
    isFetching: false,
  }),
}));

describe("FleetMemberPanel", () => {
  beforeEach(() => {
    removeMemberMutation.error = null;
    removeMemberMutation.mutateAsync.mockClear();
    removeMemberMutation.reset.mockClear();
    seedFleetStores();
  });

  it("renders members, opens the add dialog, and removes a member with confirmation", async () => {
    renderWithProviders(<FleetMemberPanel fleetId="fleet-1" />);

    expect(screen.getByText("Triage Lead")).toBeInTheDocument();
    expect(screen.getByText("Observer One")).toBeInTheDocument();
    expect(screen.getByText("Error surfaced")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /add member/i }));
    expect(screen.getByRole("heading", { name: "Add member" })).toBeInTheDocument();
    expect(screen.getByText("New Worker")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /remove triage lead/i }));
    expect(screen.getByText("Confirm removal")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Remove member" }));
    expect(removeMemberMutation.mutateAsync).toHaveBeenCalledWith({
      fleetId: "fleet-1",
      memberId: "member-1",
    });
  });

  it("surfaces conflict messaging when the API reports active executions", () => {
    removeMemberMutation.error = new ApiError(
      "conflict",
      "Member still has active executions.",
      409,
      [],
      { active_executions: 3 },
    );

    renderWithProviders(<FleetMemberPanel fleetId="fleet-1" />);

    fireEvent.click(screen.getByRole("button", { name: /remove worker one/i }));
    expect(screen.getByText(/Active executions: 3/i)).toBeInTheDocument();
  });
});
