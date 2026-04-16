import { screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { QueueBacklogChart } from "@/components/features/operator/QueueBacklogChart";
import { renderWithProviders } from "@/test-utils/render";
import { sampleQueueLagTopics } from "@/__tests__/features/operator/test-helpers";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({
    children,
  }: {
    children: React.ReactNode;
  }) => <div data-testid="responsive-container">{children}</div>,
  BarChart: ({
    children,
    data,
  }: {
    children: React.ReactNode;
    data: { topic: string }[];
  }) => (
    <div data-testid="bar-chart">
      {data.map((entry) => (
        <span key={entry.topic}>{entry.topic}</span>
      ))}
      {children}
    </div>
  ),
  Bar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Cell: ({ fill }: { fill: string }) => <span data-fill={fill} data-testid="bar-cell" />,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

describe("QueueBacklogChart", () => {
  it("renders topics and uses warning fill for high-lag bars", () => {
    const { container } = renderWithProviders(
      <QueueBacklogChart
        data={sampleQueueLagTopics}
        isLoading={false}
      />,
    );

    expect(screen.getByText("Queue backlog")).toBeInTheDocument();
    expect(container.innerHTML).toContain("orchestration.primary");
    expect(container.innerHTML).toContain("attention.requests");
    expect(
      container.querySelectorAll('[data-fill="hsl(var(--warning))"]'),
    ).toHaveLength(1);
    expect(
      container.querySelectorAll('[data-fill="hsl(var(--brand-primary))"]').length,
    ).toBeGreaterThan(0);
  });

  it("renders the retry state when backlog data is unavailable", () => {
    renderWithProviders(
      <QueueBacklogChart data={[]} error isLoading={false} />,
    );

    expect(screen.getByText("Backlog data unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
