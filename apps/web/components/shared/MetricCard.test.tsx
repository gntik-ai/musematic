import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCard } from "@/components/shared/MetricCard";

describe("MetricCard", () => {
  it("renders the metric value and unit", () => {
    render(<MetricCard title="Latency" unit="ms" value={128} />);
    expect(screen.getByText("Latency")).toBeInTheDocument();
    expect(screen.getByText("128")).toBeInTheDocument();
    expect(screen.getByText("ms")).toBeInTheDocument();
  });

  it("shows loading state", () => {
    render(<MetricCard isLoading title="Latency" value={128} />);
    expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });
});
