import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentCard } from "@/components/features/marketplace/agent-card";
import { marketplaceFixtures } from "@/mocks/handlers/marketplace";
import { useComparisonStore } from "@/lib/stores/use-comparison-store";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("AgentCard", () => {
  const agent = marketplaceFixtures.agents[0]!;

  beforeEach(() => {
    push.mockReset();
    useComparisonStore.getState().clear();
  });

  it("toggles compare state", async () => {
    const user = userEvent.setup();
    const onToggleCompare = vi.fn();

    render(
      <AgentCard
        agent={agent}
        href="/marketplace/finance-ops/kyc-verifier"
        isSelected={false}
        onToggleCompare={onToggleCompare}
      />,
    );

    await user.click(screen.getByRole("button", { name: /compare/i }));

    expect(onToggleCompare).toHaveBeenCalledWith(agent.fqn);
  });

  it("disables comparison when four other agents are already selected", () => {
    useComparisonStore.setState({
      selectedFqns: ["a:1", "a:2", "a:3", "a:4"],
    });

    render(
      <AgentCard
        agent={agent}
        href="/marketplace/finance-ops/kyc-verifier"
        isSelected={false}
        onToggleCompare={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /compare/i })).toBeDisabled();
  });

  it("navigates to the detail page on Enter", () => {
    render(
      <AgentCard
        agent={agent}
        href="/marketplace/finance-ops/kyc-verifier"
        isSelected={false}
        onToggleCompare={vi.fn()}
      />,
    );

    fireEvent.keyDown(screen.getByRole("link"), { key: "Enter" });

    expect(push).toHaveBeenCalledWith("/marketplace/finance-ops/kyc-verifier");
  });
});
