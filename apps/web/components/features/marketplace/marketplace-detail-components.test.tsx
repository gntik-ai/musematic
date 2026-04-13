import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TrustSignalsPanel } from "@/components/features/marketplace/trust-signals-panel";
import { AgentRevisions } from "@/components/features/marketplace/agent-revisions";
import { PolicyList } from "@/components/features/marketplace/policy-list";
import { QualityMetrics } from "@/components/features/marketplace/quality-metrics";
import { AgentDetail } from "@/components/features/marketplace/agent-detail";
import { renderWithProviders } from "@/test-utils/render";
import { marketplaceFixtures } from "@/mocks/handlers/marketplace";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("Marketplace detail components", () => {
  const agent = marketplaceFixtures.agents[0]!;

  it("renders trust signals", () => {
    render(<TrustSignalsPanel trustSignals={agent.trustSignals} />);

    expect(screen.getByText("Trust posture")).toBeInTheDocument();
    expect(screen.getByText("Tier progression")).toBeInTheDocument();
  });

  it("renders revision history", () => {
    render(
      <AgentRevisions
        currentVersion={agent.currentRevision}
        revisions={agent.revisions}
      />,
    );

    expect(screen.getByText(agent.currentRevision)).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
  });

  it("renders policies and quality metrics", () => {
    render(
      <>
        <PolicyList policies={agent.policies} />
        <QualityMetrics metrics={agent.qualityMetrics} />
      </>,
    );

    expect(screen.getByText(agent.policies[0]!.name)).toBeInTheDocument();
    expect(screen.getByText("Evaluation score")).toBeInTheDocument();
  });

  it("renders tabs and hides analytics for non-owners", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AgentDetail agent={agent} isOwner={false} />);

    expect(screen.getByRole("button", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Policies" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analytics" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Policies" }));
    expect(screen.getByText(agent.policies[0]!.name)).toBeInTheDocument();
  });

  it("disables start conversation when the agent is not visible", () => {
    renderWithProviders(
      <AgentDetail
        agent={{
          ...agent,
          visibility: {
            ...agent.visibility,
            visibleToCurrentUser: false,
          },
        }}
        isOwner={false}
      />,
    );

    expect(
      screen.getByRole("button", { name: /start conversation/i }),
    ).toBeDisabled();
  });
});
