import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FleetControlsPanel } from "@/components/features/fleet/FleetControlsPanel";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleGovernanceChain,
  sampleMembers,
  sampleOrchestrationRules,
  samplePersonalityProfile,
  seedFleetStores,
} from "@/__tests__/features/fleet/test-helpers";

const pauseMutation = {
  isPending: false,
  mutateAsync: vi.fn().mockResolvedValue({ status: "pausing", active_executions: 1 }),
};
const resumeMutation = {
  isPending: false,
  mutateAsync: vi.fn().mockResolvedValue({ status: "active" }),
};
const triggerStressTest = {
  isPending: false,
  mutateAsync: vi.fn().mockResolvedValue({ simulation_run_id: "run-1", status: "running" }),
};
const stressProgress = {
  data: {
    simulation_run_id: "run-1",
    status: "running",
    elapsed_seconds: 45,
    total_seconds: 900,
    simulated_executions: 32,
    current_success_rate: 0.81,
    current_avg_latency_ms: 1210,
  },
};
const cancelStressTest = {
  isPending: false,
  mutateAsync: vi.fn().mockResolvedValue({ status: "cancelled" }),
};

vi.mock("@/lib/hooks/use-fleet-actions", () => ({
  usePauseFleet: () => pauseMutation,
  useResumeFleet: () => resumeMutation,
}));

vi.mock("@/lib/hooks/use-fleet-governance", () => ({
  useFleetGovernance: () => ({ data: sampleGovernanceChain }),
  useFleetOrchestration: () => ({ data: sampleOrchestrationRules }),
  useFleetPersonality: () => ({ data: samplePersonalityProfile }),
}));

vi.mock("@/lib/hooks/use-stress-test", () => ({
  useTriggerStressTest: () => triggerStressTest,
  useStressTestProgress: (runId: string | null) => (runId ? stressProgress : { data: undefined }),
  useCancelStressTest: () => cancelStressTest,
}));

vi.mock("@/lib/hooks/use-agents", () => ({
  useAgents: () => ({
    agents: [],
    isFetching: false,
  }),
}));

vi.mock("@/lib/hooks/use-fleet-members", () => ({
  useAddFleetMember: () => ({
    isPending: false,
    mutateAsync: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("FleetControlsPanel", () => {
  beforeEach(() => {
    pauseMutation.mutateAsync.mockClear();
    resumeMutation.mutateAsync.mockClear();
    triggerStressTest.mutateAsync.mockClear();
    cancelStressTest.mutateAsync.mockClear();
    seedFleetStores();
  });

  it("shows pause for active fleets and starts the pause mutation after confirmation", () => {
    renderWithProviders(
      <FleetControlsPanel currentStatus="active" fleetId="fleet-1" members={sampleMembers} />,
    );

    expect(screen.getByRole("button", { name: /pause fleet/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resume fleet/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /pause fleet/i }));
    fireEvent.click(screen.getAllByRole("button", { name: /pause fleet/i })[1]!);

    expect(pauseMutation.mutateAsync).toHaveBeenCalledWith({ fleetId: "fleet-1" });
  });

  it("shows resume for paused fleets and transitions stress test dialog into progress view", async () => {
    renderWithProviders(
      <FleetControlsPanel currentStatus="paused" fleetId="fleet-1" members={sampleMembers} />,
    );

    expect(screen.getByRole("button", { name: /resume fleet/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /stress test fleet/i }));
    expect(screen.getByRole("heading", { name: "Stress test" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start test" }));

    await waitFor(() => {
      expect(triggerStressTest.mutateAsync).toHaveBeenCalledWith({
        durationMinutes: 15,
        fleetId: "fleet-1",
        loadLevel: "medium",
      });
    });
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByText((_, element) => element?.textContent === "Executions: 32"),
    ).toBeInTheDocument();
  });
});
