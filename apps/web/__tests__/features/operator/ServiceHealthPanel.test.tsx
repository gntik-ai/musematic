import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ServiceHealthPanel } from "@/components/features/operator/ServiceHealthPanel";
import { renderWithProviders } from "@/test-utils/render";
import { sampleServiceHealthSnapshot } from "@/__tests__/features/operator/test-helpers";

function getIndicatorCard(label: string) {
  return screen.getByText(label).closest('[class*="rounded-xl"]');
}

describe("ServiceHealthPanel", () => {
  it("renders 12 service indicators with status-specific color dots", () => {
    vi.setSystemTime(new Date("2026-04-16T12:05:00.000Z"));

    renderWithProviders(
      <ServiceHealthPanel
        isLoading={false}
        snapshot={sampleServiceHealthSnapshot}
      />,
    );

    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getByText("Redis")).toBeInTheDocument();
    expect(screen.getByText("Kafka")).toBeInTheDocument();
    expect(screen.getByText("Qdrant")).toBeInTheDocument();
    expect(screen.getByText("Neo4j")).toBeInTheDocument();
    expect(screen.getByText("ClickHouse")).toBeInTheDocument();
    expect(screen.getByText("OpenSearch")).toBeInTheDocument();
    expect(screen.getByText("MinIO")).toBeInTheDocument();
    expect(screen.getByText("Runtime Controller")).toBeInTheDocument();
    expect(screen.getByText("Reasoning Engine")).toBeInTheDocument();
    expect(screen.getByText("Sandbox Manager")).toBeInTheDocument();
    expect(screen.getByText("Simulation Controller")).toBeInTheDocument();
    expect(screen.getByText("degraded")).toBeInTheDocument();

    expect(
      getIndicatorCard("PostgreSQL")?.querySelector('[class*="bg-emerald-500"]'),
    ).not.toBeNull();
    expect(
      getIndicatorCard("Kafka")?.querySelector('[class*="bg-amber-500"]'),
    ).not.toBeNull();
    expect(
      getIndicatorCard("Neo4j")?.querySelector('[class*="bg-rose-500"]'),
    ).not.toBeNull();
    expect(
      getIndicatorCard("OpenSearch")?.querySelector('[class*="bg-slate-400"]'),
    ).not.toBeNull();
  });

  it("renders skeletons while the snapshot is loading", () => {
    const { container } = renderWithProviders(
      <ServiceHealthPanel isLoading snapshot={undefined} />,
    );

    expect(container.querySelectorAll(".animate-pulse")).toHaveLength(12);
  });
});
