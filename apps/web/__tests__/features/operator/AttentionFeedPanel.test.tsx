import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AttentionFeedPanel } from "@/components/features/operator/AttentionFeedPanel";
import { useAttentionFeedStore } from "@/lib/stores/use-attention-feed-store";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleAttentionEvents,
  seedOperatorStores,
} from "@/__tests__/features/operator/test-helpers";

const navigationMocks = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => navigationMocks,
}));

vi.mock("@/lib/hooks/use-attention-feed", () => ({
  useAttentionFeed: () => ({
    isLoading: false,
  }),
}));

describe("AttentionFeedPanel", () => {
  beforeEach(() => {
    navigationMocks.push.mockReset();
    seedOperatorStores();
    useAttentionFeedStore.setState({
      events: sampleAttentionEvents,
    });
  });

  it("renders pending events newest-first, highlights critical entries, and routes by target type", () => {
    renderWithProviders(<AttentionFeedPanel />);

    expect(screen.getByText("3 pending")).toBeInTheDocument();
    expect(
      screen.queryByText("Previously acknowledged follow-up event."),
    ).not.toBeInTheDocument();

    const items = screen.getAllByRole("button");
    const executionItem = items[0]!;
    const interactionItem = items[1]!;
    const goalItem = items[2]!;

    expect(executionItem).toHaveTextContent("risk:fraud-monitor");
    expect(interactionItem).toHaveTextContent("risk:conversation-bot");
    expect(goalItem).toHaveTextContent("risk:goal-planner");
    expect(executionItem.className).toContain("border-l-4");

    fireEvent.click(executionItem);
    expect(navigationMocks.push).toHaveBeenCalledWith(
      "/operator/executions/exec-run-0001",
    );

    fireEvent.click(interactionItem);
    expect(navigationMocks.push).toHaveBeenCalledWith("/conversations/conv-22");

    fireEvent.click(goalItem);
    expect(navigationMocks.push).toHaveBeenCalledWith("/workspaces/goals/goal-7");
  });
});
