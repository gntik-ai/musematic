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
});
