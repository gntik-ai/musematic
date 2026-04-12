import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageList } from "@/components/features/conversations/MessageList";
import { getConversationFixtures } from "@/tests/mocks/handlers";
import { renderWithProviders } from "@/test-utils/render";
import { useConversationStore } from "@/lib/stores/conversation-store";

describe("MessageList", () => {
  it("renders conversation messages with the expected aria contract", () => {
    useConversationStore.setState({
      ...useConversationStore.getState(),
      isAgentProcessing: true,
      pendingMessageCount: 2,
    });

    const messages = getConversationFixtures().interactionMessages["interaction-1"];

    renderWithProviders(
      <MessageList
        getStreamingContent={() => undefined}
        messages={messages}
      />,
    );

    expect(
      screen.getByRole("log", { name: /conversation messages/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/agent is typing/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /2 new messages, scroll to bottom/i }),
    ).toBeInTheDocument();
  });
});
