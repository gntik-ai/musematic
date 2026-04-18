import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SimulationDetailView } from "@/components/features/simulations/SimulationDetailView";
import { SimulationRunDataTable } from "@/components/features/simulations/SimulationRunDataTable";
import { renderWithProviders } from "@/test-utils/render";
import type {
  DigitalTwinResponse,
  SimulationRunResponse,
} from "@/types/simulation";

const mutationMocks = vi.hoisted(() => ({
  cancelRun: vi.fn(),
  createComparison: vi.fn(),
}));

vi.mock("@/lib/hooks/use-simulation-mutations", () => ({
  useSimulationMutations: () => ({
    cancelRun: {
      mutateAsync: mutationMocks.cancelRun,
      isPending: false,
      error: null,
    },
    createComparison: {
      mutateAsync: mutationMocks.createComparison,
      isPending: false,
      error: null,
    },
    createRun: {
      mutateAsync: vi.fn(),
      isPending: false,
      error: null,
    },
  }),
}));

const simulationRuns: [SimulationRunResponse, SimulationRunResponse, SimulationRunResponse] = [
  {
    run_id: "sim-run-1",
    workspace_id: "workspace-1",
    name: "KYC Load Test",
    description: "Primary simulation",
    status: "running",
    digital_twin_ids: ["twin-1"],
    scenario_config: { duration_seconds: 600 },
    isolation_policy_id: "policy-1",
    controller_run_id: "controller-1",
    started_at: "2026-04-18T08:00:00.000Z",
    completed_at: null,
    results: null,
    initiated_by: "user-1",
    created_at: "2026-04-18T08:00:00.000Z",
  },
  {
    run_id: "sim-run-2",
    workspace_id: "workspace-1",
    name: "Payments Resilience",
    description: null,
    status: "completed",
    digital_twin_ids: ["twin-2", "twin-3"],
    scenario_config: {},
    isolation_policy_id: null,
    controller_run_id: "controller-2",
    started_at: "2026-04-18T07:00:00.000Z",
    completed_at: "2026-04-18T07:30:00.000Z",
    results: { latency_ms: 82 },
    initiated_by: "user-1",
    created_at: "2026-04-18T07:00:00.000Z",
  },
  {
    run_id: "sim-run-3",
    workspace_id: "workspace-1",
    name: "Escalation Chaos",
    description: null,
    status: "failed",
    digital_twin_ids: ["twin-4"],
    scenario_config: {},
    isolation_policy_id: null,
    controller_run_id: "controller-3",
    started_at: "2026-04-18T06:00:00.000Z",
    completed_at: "2026-04-18T06:15:00.000Z",
    results: null,
    initiated_by: "user-1",
    created_at: "2026-04-18T06:00:00.000Z",
  },
];

const digitalTwins: DigitalTwinResponse[] = [
  {
    twin_id: "twin-1",
    workspace_id: "workspace-1",
    source_agent_fqn: "finance:kyc",
    source_revision_id: "rev-1",
    version: 1,
    parent_twin_id: null,
    config_snapshot: {},
    behavioral_history_summary: {},
    modifications: [{ type: "prompt_patch" }],
    is_active: true,
    created_at: "2026-04-18T05:00:00.000Z",
    warning_flags: ["stale baseline"],
  },
];

function SimulationTableHarness({
  onCompare,
  onCreate,
  onLoadMore,
  onRowClick,
}: {
  onCompare: (runIds: [string, string]) => void;
  onCreate: () => void;
  onLoadMore: () => void;
  onRowClick: (runId: string) => void;
}) {
  const [selectedRunIds, setSelectedRunIds] = useState(new Set<string>());

  return (
    <SimulationRunDataTable
      nextCursor="cursor-2"
      onCompare={onCompare}
      onCreate={onCreate}
      onLoadMore={onLoadMore}
      onRowClick={onRowClick}
      onSelectionChange={setSelectedRunIds}
      runs={simulationRuns}
      selectedRunIds={selectedRunIds}
    />
  );
}

describe("SimulationRunDataTable", () => {
  it("keeps at most two selections and forwards compare, load, and row actions", async () => {
    const onCompare = vi.fn();
    const onCreate = vi.fn();
    const onLoadMore = vi.fn();
    const onRowClick = vi.fn();

    renderWithProviders(
      <SimulationTableHarness
        onCompare={onCompare}
        onCreate={onCreate}
        onLoadMore={onLoadMore}
        onRowClick={onRowClick}
      />,
    );

    fireEvent.click(
      screen.getByLabelText("Select simulation KYC Load Test for comparison"),
    );
    await waitFor(() => {
      expect(
        screen.getByLabelText("Select simulation KYC Load Test for comparison"),
      ).toBeChecked();
    });

    fireEvent.click(
      screen.getByLabelText(
        "Select simulation Payments Resilience for comparison",
      ),
    );
    await waitFor(() => {
      expect(
        screen.getByLabelText("Select simulation Payments Resilience for comparison"),
      ).toBeChecked();
    });

    fireEvent.click(
      screen.getByLabelText("Select simulation Escalation Chaos for comparison"),
    );
    await waitFor(() => {
      expect(
        screen.getByLabelText("Select simulation KYC Load Test for comparison"),
      ).not.toBeChecked();
      expect(
        screen.getByLabelText("Select simulation Payments Resilience for comparison"),
      ).toBeChecked();
      expect(
        screen.getByLabelText("Select simulation Escalation Chaos for comparison"),
      ).toBeChecked();
    });

    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    expect(onCompare).toHaveBeenCalledWith(["sim-run-2", "sim-run-3"]);

    fireEvent.click(screen.getByText("Payments Resilience"));
    expect(onRowClick).toHaveBeenCalledWith("sim-run-2");

    fireEvent.click(screen.getByRole("button", { name: "Load More" }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Create Simulation" }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });
});

describe("SimulationDetailView", () => {
  beforeEach(() => {
    mutationMocks.cancelRun.mockReset();
    mutationMocks.createComparison.mockReset();
    mutationMocks.cancelRun.mockResolvedValue(undefined);
    mutationMocks.createComparison.mockResolvedValue({ report_id: "report-42" });
  });

  it("creates a production comparison and confirms simulation cancellation", async () => {
    const onComparisonCreated = vi.fn();

    renderWithProviders(
      <SimulationDetailView
        onComparisonCreated={onComparisonCreated}
        run={simulationRuns[0]}
        twins={digitalTwins}
      />,
    );

    expect(screen.getByText("SIMULATION")).toBeInTheDocument();
    expect(screen.getByText("running")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("finance:kyc v1")).toBeInTheDocument();
    expect(screen.getByText("stale baseline")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Compare with Production" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Last 30 days" }));

    await waitFor(() => {
      expect(mutationMocks.createComparison).toHaveBeenCalledWith({
        primaryRunId: "sim-run-1",
        productionBaselinePeriod: { preset: "last_30_days" },
        comparisonType: "simulation_vs_production",
      });
    });

    expect(onComparisonCreated).toHaveBeenCalledWith(
      "report-42",
      "simulation_vs_production",
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.getByText("Cancel this simulation? This cannot be undone."),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Cancel simulation" }),
    );

    await waitFor(() => {
      expect(mutationMocks.cancelRun).toHaveBeenCalledWith("sim-run-1");
    });
  });
});
