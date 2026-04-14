import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InteractionTabs } from "@/components/features/conversations/InteractionTabs";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { getConversationFixtures } from "@/tests/mocks/handlers";
import { renderWithProviders } from "@/test-utils/render";

describe("InteractionTabs", () => {
  it("switches interactions and shows unread indicators", async () => {
    const user = userEvent.setup();
    const conversation = getConversationFixtures().conversations[0];
    if (!conversation) {
      throw new Error("Expected a conversation fixture");
    }
    const onInteractionChange = vi.fn();

    useConversationStore.setState({
      ...useConversationStore.getState(),
      activeInteractionId: conversation.interactions[0]?.id ?? null,
      unreadInteractionIds: [conversation.interactions[1]?.id ?? ""],
    });

    renderWithProviders(
      <InteractionTabs
        conversation={conversation}
        onInteractionChange={onInteractionChange}
      />,
    );

    expect(screen.getByRole("tab", { name: /finance analyzer/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /trust reviewer/i })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /trust reviewer/i }));

    expect(onInteractionChange).toHaveBeenCalledWith("interaction-2");
  });

  it("renders branch tabs, clears branch unread state, and marks the branch as active", async () => {
    const user = userEvent.setup();
    const conversation = getConversationFixtures().conversations[0];
    if (!conversation) {
      throw new Error("Expected a conversation fixture");
    }

    useConversationStore.setState({
      ...useConversationStore.getState(),
      activeBranchId: null,
      activeInteractionId: conversation.interactions[0]?.id ?? null,
      branchTabs: [
        {
          id: "branch-1",
          interactionId: null,
          name: "Approach B",
        },
      ],
      unreadBranchIds: ["branch-1"],
    });

    renderWithProviders(
      <InteractionTabs
        conversation={conversation}
        onInteractionChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /approach b/i }));

    expect(useConversationStore.getState().activeBranchId).toBe("branch-1");
    expect(useConversationStore.getState().unreadBranchIds).toEqual([]);
    expect(screen.getByRole("button", { name: /branch view is active/i })).toBeInTheDocument();
  });
});
