import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AgentCardGrid } from "@/components/features/marketplace/agent-card-grid";
import { marketplaceFixtures } from "@/mocks/handlers/marketplace";
import { useComparisonStore } from "@/lib/stores/use-comparison-store";
import { renderWithProviders } from "@/test-utils/render";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("AgentCardGrid", () => {
  it("renders loading skeletons", () => {
    const { container } = renderWithProviders(
      <AgentCardGrid
        agents={[]}
        hasNextPage={false}
        isError={false}
        isFetchingNextPage={false}
        isLoading
        onLoadMore={vi.fn()}
      />,
    );

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("renders the empty state when there are no agents", () => {
    renderWithProviders(
      <AgentCardGrid
        agents={[]}
        hasNextPage={false}
        isError={false}
        isFetchingNextPage={false}
        isLoading={false}
        onLoadMore={vi.fn()}
      />,
    );

    expect(screen.getByText("No agents match your search")).toBeInTheDocument();
  });

  it("renders agent cards", () => {
    useComparisonStore.getState().clear();

    renderWithProviders(
      <AgentCardGrid
        agents={marketplaceFixtures.agents.slice(0, 2)}
        hasNextPage={false}
        isError={false}
        isFetchingNextPage={false}
        isLoading={false}
        onLoadMore={vi.fn()}
      />,
    );

    expect(screen.getByText(marketplaceFixtures.agents[0]!.displayName)).toBeInTheDocument();
    expect(screen.getByText(marketplaceFixtures.agents[1]!.displayName)).toBeInTheDocument();
  });
});
