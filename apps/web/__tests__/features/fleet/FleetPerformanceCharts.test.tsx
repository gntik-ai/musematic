import { act, fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FleetPerformanceCharts } from "@/components/features/fleet/FleetPerformanceCharts";
import { renderWithProviders } from "@/test-utils/render";
import {
  samplePerformanceHistory,
  seedFleetStores,
} from "@/__tests__/features/fleet/test-helpers";

const performanceHookMock = vi.fn();
const wsMocks = vi.hoisted(() => {
  let eventHandler: ((event: { payload: unknown }) => void) | null = null;
  return {
    connect: vi.fn(),
    emit: (payload: unknown) => eventHandler?.({ payload }),
    subscribe: vi.fn((_channel: string, handler: (event: { payload: unknown }) => void) => {
      eventHandler = handler;
      return vi.fn();
    }),
  };
});

vi.mock("recharts", () => ({
  CartesianGrid: () => null,
  Line: () => null,
  LineChart: ({ children, data, syncId }: { children: React.ReactNode; data: unknown[]; syncId?: string }) => (
    <div data-points={data.length} data-syncid={syncId} data-testid="line-chart">
      {children}
    </div>
  ),
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

vi.mock("@/lib/hooks/use-fleet-performance", () => ({
  useFleetPerformanceHistory: (fleetId: string, range: string) => {
    performanceHookMock(fleetId, range);
    return {
      data: samplePerformanceHistory,
      isLoading: false,
    };
  },
}));

vi.mock("@/lib/ws", () => ({
  wsClient: wsMocks,
}));

describe("FleetPerformanceCharts", () => {
  beforeEach(() => {
    performanceHookMock.mockClear();
    seedFleetStores();
  });

  it("renders the three charts, changes time range, and appends realtime data", () => {
    renderWithProviders(<FleetPerformanceCharts fleetId="fleet-1" />);

    expect(screen.getAllByTestId("line-chart")).toHaveLength(3);
    expect(screen.getAllByTestId("line-chart")[0]).toHaveAttribute("data-syncid", "fleet-perf");

    fireEvent.click(screen.getByRole("button", { name: "7d" }));
    expect(performanceHookMock).toHaveBeenLastCalledWith("fleet-1", "7d");

    act(() => {
      wsMocks.emit({
        performance_profile: {
          ...samplePerformanceHistory[0],
          id: "perf-3",
          period_start: "2026-04-16T11:00:00.000Z",
          period_end: "2026-04-16T12:00:00.000Z",
        },
      });
    });

    expect(screen.getAllByTestId("line-chart")[0]).toHaveAttribute("data-points", "3");
  });
});

