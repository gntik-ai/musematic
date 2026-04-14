import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MessageList } from "@/components/features/conversations/MessageList";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { getConversationFixtures } from "@/tests/mocks/handlers";

const {
  bubbleSpy,
  scrollToBottomSpy,
  virtualizerState,
} = vi.hoisted(() => ({
  bubbleSpy: vi.fn(),
  scrollToBottomSpy: vi.fn(),
  virtualizerState: {
    items: [
      { index: 0, key: "message-1", start: 0 },
      { index: 1, key: "message-2", start: 96 },
    ],
  },
}));

vi.mock("@tanstack/react-virtual", () => ({
  useVirtualizer: () => ({
    getTotalSize: () => 192,
    getVirtualItems: () => virtualizerState.items,
    measureElement: vi.fn(),
  }),
}));

vi.mock("@/lib/hooks/use-auto-scroll", () => ({
  useAutoScroll: () => ({
    containerRef: { current: null },
    sentinelRef: { current: null },
    scrollToBottom: scrollToBottomSpy,
  }),
}));

vi.mock("@/components/features/conversations/MessageBubble", () => ({
  MessageBubble: (props: {
    isStreaming?: boolean;
    message: { id: string };
    onBranchFrom?: () => void;
    showBranchOriginIndicator?: boolean;
  }) => {
    bubbleSpy(props);
    return (
      <button onClick={() => props.onBranchFrom?.()} type="button">
        bubble {props.message.id} {props.isStreaming ? "streaming" : "static"}{" "}
        {props.showBranchOriginIndicator ? "branch" : "plain"}
      </button>
    );
  },
}));

vi.mock("@/components/features/conversations/NewMessagesPill", () => ({
  NewMessagesPill: ({ count, onClick }: { count: number; onClick: () => void }) => (
    <button onClick={onClick} type="button">
      pill {count}
    </button>
  ),
}));

vi.mock("@/components/features/conversations/TypingIndicator", () => ({
  TypingIndicator: () => <div>Typing indicator</div>,
}));

describe("MessageList behavior", () => {
  beforeEach(() => {
    bubbleSpy.mockReset();
    scrollToBottomSpy.mockReset();
    virtualizerState.items = [
      { index: 0, key: "message-1", start: 0 },
      { index: 1, key: "message-2", start: 96 },
    ];
    useConversationStore.getState().reset();
  });

  it("renders virtualized messages, typing state, and branch actions", async () => {
    const fixtures = getConversationFixtures();
    const messages = fixtures.interactionMessages["interaction-1"] ?? [];
    const onBranchFromMessage = vi.fn();
    const user = userEvent.setup();

    useConversationStore.setState({
      ...useConversationStore.getState(),
      autoScrollEnabled: true,
      isAgentProcessing: true,
      pendingMessageCount: 2,
    });

    render(
      <MessageList
        branchOriginMessageIds={new Set(["message-1"])}
        getStreamingContent={(messageId) =>
          messageId === "message-2" ? "partial content" : undefined
        }
        messages={messages}
        onBranchFromMessage={onBranchFromMessage}
      />,
    );

    expect(scrollToBottomSpy).toHaveBeenCalled();
    expect(screen.getByText("Typing indicator")).toBeInTheDocument();
    expect(screen.getByText("pill 2")).toBeInTheDocument();
    expect(bubbleSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        isStreaming: true,
        showBranchOriginIndicator: false,
      }),
    );

    await user.click(screen.getByRole("button", { name: /bubble message-1/i }));
    expect(onBranchFromMessage).toHaveBeenCalledWith("message-1");
  });

  it("skips missing virtual items and does not autoscroll when paused", () => {
    const fixtures = getConversationFixtures();
    virtualizerState.items = [{ index: 99, key: "missing", start: 0 }];

    useConversationStore.setState({
      ...useConversationStore.getState(),
      autoScrollEnabled: false,
      isAgentProcessing: false,
      pendingMessageCount: 0,
    });

    render(
      <MessageList
        getStreamingContent={() => undefined}
        messages={fixtures.interactionMessages["interaction-1"] ?? []}
      />,
    );

    expect(scrollToBottomSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("Typing indicator")).not.toBeInTheDocument();
    expect(bubbleSpy).not.toHaveBeenCalled();
  });
});
