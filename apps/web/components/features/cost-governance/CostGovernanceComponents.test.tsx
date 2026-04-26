import { render, screen } from "@testing-library/react";
import type React from "react";
import { describe, expect, it, vi } from "vitest";
import { BudgetThresholdGauge, budgetThresholdTone } from "./BudgetThresholdGauge";
import { budgetConfigSchema } from "./BudgetConfigForm";
import { ForecastChart } from "./ForecastChart";

vi.mock("recharts", () => ({
  Area: () => null,
  AreaChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => null,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CartesianGrid: () => null,
  Line: () => null,
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Tooltip: () => null,
  XAxis: () => null,
  YAxis: () => null,
}));

describe("cost governance components", () => {
  it("classifies budget threshold colors at 50, 80, and 100 percent", () => {
    expect(budgetThresholdTone(50)).toBe("ok");
    expect(budgetThresholdTone(80)).toBe("warn");
    expect(budgetThresholdTone(100)).toBe("danger");
  });

  it("renders the budget threshold gauge", () => {
    render(<BudgetThresholdGauge budgetCents={10000} currentSpendCents={8000} thresholds={[50, 80, 100]} />);

    expect(screen.getByText("$80.00")).toBeInTheDocument();
    expect(screen.getByText("80.0%")).toBeInTheDocument();
  });

  it("validates sorted threshold configuration", () => {
    const valid = budgetConfigSchema.safeParse({
      period_type: "monthly",
      budget_cents: 10000,
      thresholds: "50,80,100",
      hard_cap_enabled: true,
      admin_override_enabled: true,
    });
    const invalid = budgetConfigSchema.safeParse({
      period_type: "monthly",
      budget_cents: 10000,
      thresholds: "80,50,101",
      hard_cap_enabled: true,
      admin_override_enabled: true,
    });

    expect(valid.success).toBe(true);
    expect(invalid.success).toBe(false);
  });

  it("shows the low-confidence forecast empty state", () => {
    render(
      <ForecastChart
        forecast={{
          id: "forecast-1",
          workspace_id: "workspace-1",
          period_start: "2026-04-01T00:00:00Z",
          period_end: "2026-04-30T00:00:00Z",
          forecast_cents: null,
          confidence_interval: { status: "insufficient_history" },
          currency: "USD",
          computed_at: "2026-04-26T00:00:00Z",
        }}
      />,
    );

    expect(screen.getByText("Insufficient history")).toBeInTheDocument();
  });
});
