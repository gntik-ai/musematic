import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { RecommendationCarousel } from "@/components/features/marketplace/recommendation-carousel";
import { CreatorAnalyticsTab } from "@/components/features/marketplace/creator-analytics-tab";
import { UsageChart } from "@/components/features/marketplace/usage-chart";
import { SatisfactionTrendChart } from "@/components/features/marketplace/satisfaction-trend-chart";
import { marketplaceFixtures } from "@/mocks/handlers/marketplace";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("Marketplace analytics and recommendations", () => {
  it("renders the recommendation carousel when at least three agents exist", () => {
    render(
      <RecommendationCarousel
        data={marketplaceFixtures.recommendations}
        isLoading={false}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Recommended agents" }),
    ).toBeInTheDocument();
  });

  it("returns null when fewer than three recommendations exist", () => {
    const { container } = render(
      <RecommendationCarousel
        data={{
          ...marketplaceFixtures.recommendations,
          agents: marketplaceFixtures.recommendations.agents.slice(0, 2),
        }}
        isLoading={false}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders an empty state when creator analytics is empty", async () => {
    const agent = marketplaceFixtures.agents[0]!;

    server.use(
      http.get("*/api/v1/marketplace/agents/:namespace/:name/analytics", () =>
        HttpResponse.json({
          agentFqn: agent.fqn,
          periodDays: 30,
          usageChart: [],
          satisfactionTrend: [],
          commonFailures: [],
        }),
      ),
    );

    renderWithProviders(<CreatorAnalyticsTab agentFqn={agent.fqn} />);

    expect(await screen.findByText("No usage data yet")).toBeInTheDocument();
  });

  it("renders usage and satisfaction charts", () => {
    const analytics = marketplaceFixtures.analyticsByFqn[marketplaceFixtures.agents[0]!.fqn]!;

    render(
      <>
        <UsageChart data={analytics.usageChart} periodDays={analytics.periodDays} />
        <SatisfactionTrendChart data={analytics.satisfactionTrend} />
      </>,
    );

    expect(screen.getByText(/usage over/i)).toBeInTheDocument();
    expect(screen.getByText(/satisfaction trend/i)).toBeInTheDocument();
  });
});
