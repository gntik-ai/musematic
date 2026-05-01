import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DigitalTwinPanel } from "@/components/features/simulations/DigitalTwinPanel";
import { renderWithProviders } from "@/test-utils/render";
import type { DigitalTwinDivergenceReport } from "@/types/simulation";

const hookMocks = vi.hoisted(() => ({
  report: undefined as DigitalTwinDivergenceReport | undefined,
}));

vi.mock("@/lib/hooks/use-digital-twin", () => ({
  useDigitalTwin: () => ({ data: hookMocks.report }),
}));

describe("DigitalTwinPanel", () => {
  beforeEach(() => {
    hookMocks.report = undefined;
  });

  it("renders mock and real components with divergence highlights", () => {
    hookMocks.report = {
      run_id: "run-1",
      mock_components: ["tool-gateway", "llm-provider"],
      real_components: ["memory-store"],
      divergence_points: [{ metric: "latency_ms", delta: 42 }],
      simulated_time_ms: 2500,
      wall_clock_time_ms: 3200,
      reference_execution_id: "exec-1",
      reference_available: true,
    };

    renderWithProviders(<DigitalTwinPanel reportId="report-1" runId="run-1" />);

    expect(screen.getByText("Mock components")).toBeInTheDocument();
    expect(screen.getByText("tool-gateway")).toBeInTheDocument();
    expect(screen.getByText("llm-provider")).toBeInTheDocument();
    expect(screen.getByText("Real components")).toBeInTheDocument();
    expect(screen.getByText("memory-store")).toBeInTheDocument();
    expect(screen.getByText("Reference exec-1")).toBeInTheDocument();
    expect(screen.getByText(/latency_ms/)).toBeInTheDocument();
  });

  it("renders the no reference available state", () => {
    hookMocks.report = {
      run_id: "run-2",
      mock_components: [],
      real_components: [],
      divergence_points: [],
      simulated_time_ms: null,
      wall_clock_time_ms: null,
      reference_execution_id: null,
      reference_available: false,
    };

    renderWithProviders(<DigitalTwinPanel runId="run-2" />);

    expect(screen.getAllByText("No components listed.")).toHaveLength(2);
    expect(screen.getByText("No reference available.")).toBeInTheDocument();
  });
});
