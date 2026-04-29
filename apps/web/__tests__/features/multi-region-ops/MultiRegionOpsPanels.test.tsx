import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import {
  ActiveWindowBanner,
  CapacityProjectionChart,
  FailoverPlanList,
  MaintenanceWindowForm,
  ReplicationStatusTable,
} from "@/components/features/multi-region-ops";
import type {
  CapacitySignalResponse,
  FailoverPlanResponse,
  MaintenanceWindowResponse,
  ReplicationStatusResponse,
} from "@/lib/api/regions";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  AreaChart: ({ children }: { children: React.ReactNode }) => <svg>{children}</svg>,
  Area: () => <path data-testid="area" />,
  CartesianGrid: () => <g data-testid="grid" />,
  LineChart: ({ children }: { children: React.ReactNode }) => <svg>{children}</svg>,
  Line: () => <path data-testid="line" />,
  ReferenceLine: () => <line data-testid="reference-line" />,
  Tooltip: () => <g data-testid="tooltip" />,
  XAxis: () => <g data-testid="x-axis" />,
  YAxis: () => <g data-testid="y-axis" />,
}));

const rows: ReplicationStatusResponse[] = [
  {
    source_region: "eu-west",
    target_region: "us-east",
    component: "postgres",
    lag_seconds: null,
    health: "paused",
    pause_reason: "planned maintenance",
    measured_at: "2026-04-20T10:00:00.000Z",
    threshold_seconds: 900,
    missing_probe: false,
  },
  {
    source_region: "eu-west",
    target_region: "us-east",
    component: "kafka",
    lag_seconds: null,
    health: "unhealthy",
    error_detail: "replication status missing",
    measured_at: null,
    threshold_seconds: 900,
    missing_probe: true,
  },
];

const stalePlan: FailoverPlanResponse = {
  id: "plan-1",
  name: "primary-to-dr",
  from_region: "eu-west",
  to_region: "us-east",
  steps: [{ kind: "custom", name: "Notify", parameters: {} }],
  runbook_url: "/docs/runbooks/failover.md",
  tested_at: null,
  last_executed_at: null,
  created_by: null,
  version: 1,
  created_at: "2026-04-20T10:00:00.000Z",
  updated_at: "2026-04-20T10:00:00.000Z",
  is_stale: true,
};

const activeWindow: MaintenanceWindowResponse = {
  id: "window-1",
  starts_at: "2099-01-01T00:00:00.000Z",
  ends_at: "2099-01-01T02:00:00.000Z",
  reason: "database maintenance",
  blocks_writes: true,
  announcement_text: "Writes are paused",
  status: "active",
  scheduled_by: null,
  enabled_at: "2099-01-01T00:00:00.000Z",
  disabled_at: null,
  disable_failure_reason: null,
  created_at: "2026-04-20T10:00:00.000Z",
  updated_at: "2026-04-20T10:00:00.000Z",
};

describe("multi-region operator panels", () => {
  it("distinguishes paused replication, outage rows, and missing probes", () => {
    render(<ReplicationStatusTable rows={rows} />);

    expect(screen.getByText("paused")).toBeInTheDocument();
    expect(screen.getByText("planned maintenance")).toBeInTheDocument();
    expect(screen.getByText("unhealthy")).toBeInTheDocument();
    expect(screen.getByText("replication status missing")).toBeInTheDocument();
  });

  it("keeps stale failover plans visible", () => {
    render(
      <FailoverPlanList
        plans={[
          stalePlan,
          {
            ...stalePlan,
            id: "plan-2",
            name: "primary-to-dr-rehearsed",
            is_stale: false,
            tested_at: "2026-04-20T10:00:00.000Z",
          },
        ]}
      />,
    );

    expect(screen.getByText("primary-to-dr")).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByText("rehearsed")).toBeInTheDocument();
  });

  it("validates maintenance windows and surfaces overlap conflicts", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const { container } = render(
      <MaintenanceWindowForm
        existingWindows={[activeWindow]}
        isSuperadmin
        onSubmit={onSubmit}
      />,
    );
    const startsInput = container.querySelector<HTMLInputElement>('input[name="starts_at"]');
    const endsInput = container.querySelector<HTMLInputElement>('input[name="ends_at"]');
    expect(startsInput).not.toBeNull();
    expect(endsInput).not.toBeNull();

    await user.type(startsInput as HTMLInputElement, "2020-01-01T00:00");
    await user.type(endsInput as HTMLInputElement, "2020-01-01T01:00");
    await user.click(screen.getByRole("button", { name: "Schedule" }));
    expect(await screen.findByText("starts_at cannot be in the past")).toBeInTheDocument();

    await user.clear(startsInput as HTMLInputElement);
    await user.clear(endsInput as HTMLInputElement);
    await user.type(startsInput as HTMLInputElement, "2099-01-01T01:00");
    await user.type(endsInput as HTMLInputElement, "2099-01-01T03:00");
    await user.click(screen.getByRole("button", { name: "Schedule" }));
    expect(
      await screen.findByText("Maintenance window overlaps with an existing window"),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("surfaces maintenance 409 conflicts from the API", () => {
    render(
      <MaintenanceWindowForm
        existingWindows={[]}
        isSuperadmin
        serverError="Maintenance window overlaps with an existing scheduled or active window"
      />,
    );

    expect(screen.getByText(/existing scheduled or active window/i)).toBeInTheDocument();
  });

  it("keeps the active-window banner mounted while countdown text updates", async () => {
    const user = userEvent.setup();
    const onDisable = vi.fn();
    const { rerender } = render(
      <ActiveWindowBanner isSuperadmin onDisable={onDisable} window={activeWindow} />,
    );

    expect(screen.getByText("Writes are paused")).toBeInTheDocument();
    expect(screen.getByText(/remaining/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Disable" }));
    expect(onDisable).toHaveBeenCalledWith("window-1");

    rerender(
      <ActiveWindowBanner
        isSuperadmin
        onDisable={onDisable}
        window={{ ...activeWindow, ends_at: "2099-01-01T03:00:00.000Z" }}
      />,
    );
    expect(screen.getByText("Writes are paused")).toBeInTheDocument();
  });

  it("renders insufficient-history and confidence interval projection states", () => {
    const insufficient: CapacitySignalResponse = {
      resource_class: "compute",
      historical_trend: [],
      projection: null,
      saturation_horizon: null,
      confidence: "insufficient_history",
      recommendation: null,
      generated_at: "2026-04-20T10:00:00.000Z",
    };
    const confident: CapacitySignalResponse = {
      ...insufficient,
      projection: { projected_utilization: 0.83 },
      saturation_horizon: { threshold: 0.8 },
      confidence: "ok",
    };

    const { rerender } = render(<CapacityProjectionChart signal={insufficient} />);
    expect(screen.getByText("Insufficient history")).toBeInTheDocument();

    rerender(<CapacityProjectionChart signal={confident} />);
    expect(screen.getByLabelText("confidence interval")).toBeInTheDocument();
    expect(screen.getByTestId("reference-line")).toBeInTheDocument();
  });
});
