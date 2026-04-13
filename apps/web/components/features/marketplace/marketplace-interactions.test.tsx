import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ComparisonView } from "@/components/features/marketplace/comparison-view";
import { StarRatingInput } from "@/components/features/marketplace/star-rating-input";
import { ReviewsSection } from "@/components/features/marketplace/reviews-section";
import { InvokeAgentDialog } from "@/components/features/marketplace/invoke-agent-dialog";
import { marketplaceFixtures } from "@/mocks/handlers/marketplace";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";
import { useWorkspaceStore } from "@/store/workspace-store";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("Marketplace interactions", () => {
  const agents = marketplaceFixtures.agents.slice(0, 2);

  beforeEach(() => {
    push.mockReset();
    useWorkspaceStore.setState({
      currentWorkspace: null,
      isLoading: false,
      sidebarCollapsed: false,
      workspaceList: [],
    });
  });

  it("shows comparison rows and remove actions", () => {
    render(<ComparisonView agents={agents} onRemove={vi.fn()} />);

    expect(screen.getByText("Display Name")).toBeInTheDocument();
    expect(screen.getByLabelText(`Remove ${agents[0]!.displayName} from comparison`)).toBeInTheDocument();
  });

  it("supports arrow-key navigation in the star input", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<StarRatingInput name="Rating" value={3} onChange={onChange} />);

    await user.click(screen.getByLabelText("Rate 3 out of 5 stars"));
    await user.keyboard("{ArrowRight}");

    expect(onChange).toHaveBeenCalledWith(4);
  });

  it("submits a review", async () => {
    const user = userEvent.setup();
    const agent = marketplaceFixtures.agents[10]!;
    const reviewText = "Fresh review for a zero-review agent";

    renderWithProviders(
      <ReviewsSection agentFqn={agent.fqn} currentUserReview={null} />,
    );

    await user.click(screen.getByLabelText("Rate 4 out of 5 stars"));
    await user.type(
      screen.getByLabelText("Review"),
      reviewText,
    );
    await user.click(screen.getByRole("button", { name: /submit review/i }));

    await waitFor(() => {
      expect(screen.getByText(reviewText)).toBeInTheDocument();
    });
  });

  it("supports the two-step invoke flow", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("*/api/v1/workspaces", () =>
        HttpResponse.json({
          items: marketplaceFixtures.workspaces,
        }),
      ),
    );

    renderWithProviders(
      <InvokeAgentDialog
        agentDisplayName="KYC Verifier"
        agentFqn="finance-ops:kyc-verifier"
        isVisible
        trigger={<button type="button">Start Conversation</button>}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Start Conversation" }));
    await user.click(screen.getByLabelText(marketplaceFixtures.workspaces[0]!.name));
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.type(
      screen.getByLabelText("Task brief"),
      "Analyze Q1 customer churn patterns",
    );
    await user.click(screen.getByRole("button", { name: /start conversation/i }));

    expect(push).toHaveBeenCalledWith(
      expect.stringContaining("/conversations/new?"),
    );
  });
});
