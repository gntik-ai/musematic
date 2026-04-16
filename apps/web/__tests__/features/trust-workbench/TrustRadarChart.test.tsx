import type { ReactNode } from "react";
import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TrustRadarChart } from "@/components/features/trust-workbench/TrustRadarChart";
import { renderWithProviders } from "@/test-utils/render";
import { sampleTrustRadarProfile } from "@/__tests__/features/trust-workbench/test-helpers";

vi.mock("recharts", () => ({
  PolarAngleAxis: () => null,
  PolarGrid: ({ gridType }: { gridType: string }) => (
    <div data-gridtype={gridType} data-testid="polar-grid" />
  ),
  PolarRadiusAxis: () => null,
  Radar: () => <div data-testid="radar-layer" />,
  RadarChart: ({
    children,
    data,
  }: {
    children: ReactNode;
    data: Array<{ subject: string; isWeak: boolean }>;
  }) => (
    <div data-count={data.length} data-testid="radar-chart">
      {children}
      {data.map((point) => (
        <span key={point.subject}>
          {point.subject}
          {point.isWeak ? " !" : ""}
        </span>
      ))}
    </div>
  ),
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  Tooltip: ({
    content,
  }: {
    content: (args: {
      active: boolean;
      payload: Array<{ value: number; payload: { dimension: string } }>;
    }) => ReactNode;
  }) => (
    <div data-testid="tooltip">
      {content({
        active: true,
        payload: [
          {
            value: 22,
            payload: { dimension: "behavioral_compliance" },
          },
        ],
      })}
    </div>
  ),
}));

describe("TrustRadarChart", () => {
  it("renders seven data points, exposes an accessible chart region, and shows tooltip content", () => {
    renderWithProviders(
      <div className="dark">
        <TrustRadarChart profile={sampleTrustRadarProfile} />
      </div>,
    );

    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      "Trust radar chart for risk:fraud-monitor",
    );
    expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
    expect(screen.getByTestId("radar-chart")).toHaveAttribute("data-count", "7");
    expect(screen.getByText(/behavioral_compliance !/i)).toBeInTheDocument();
    expect(screen.getAllByText("22 / 100").length).toBeGreaterThan(0);
    expect(screen.getByText("3 anomalies")).toBeInTheDocument();
  });
});
