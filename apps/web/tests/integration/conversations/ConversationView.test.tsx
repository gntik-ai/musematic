import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationView } from "@/components/features/conversations/ConversationView";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { getConversationFixtures } from "@/tests/mocks/handlers";

const {
  getStreamingContentSpy,
  messageListSpy,
  messagesResult,
} = vi.hoisted(() => ({
  getStreamingContentSpy: vi.fn(),
  messageListSpy: vi.fn(),
  messagesResult: {
    messages: [] as Array<{ id: string }>,
  },
}));

vi.mock("@/lib/hooks/use-message-stream", () => ({
  useMessageStream: () => ({
    getStreamingContent: getStreamingContentSpy,
  }),
}));

vi.mock("@/lib/hooks/use-messages", () => ({
  useMessages: () => messagesResult,
}));

vi.mock("@/components/features/conversations/InteractionTabs", () => ({
  InteractionTabs: ({ conversation, onInteractionChange }: {
    conversation: { interactions: Array<{ id: string }> };
    onInteractionChange: (id: string) => void;
  }) => (
    <button onClick={() => onInteractionChange(conversation.interactions[1]?.id ?? "none")} type="button">
      Change interaction
    </button>
  ),
}));

vi.mock("@/components/features/conversations/StatusBar", () => ({
  StatusBar: ({ interaction, isProcessing }: { interaction: { id: string }; isProcessing: boolean }) => (
    <div>
      Status for {interaction.id} {isProcessing ? "processing" : "idle"}
    </div>
  ),
}));

vi.mock("@/components/features/conversations/MessageList", () => ({
  MessageList: (props: {
    messages: Array<{ id: string }>;
    onBranchFromMessage?: (messageId: string) => void;
  }) => {
    messageListSpy(props);
    return (
      <button
        onClick={() => props.onBranchFromMessage?.(props.messages[0]?.id ?? "missing-message")}
        type="button"
      >
        Branch from visible message
      </button>
    );
  },
}));

vi.mock("@/components/features/conversations/MessageInput", () => ({
  MessageInput: ({ conversationId, interactionId }: { conversationId: string; interactionId: string }) => (
    <div>
      Input for {conversationId}/{interactionId}
    </div>
  ),
}));

vi.mock("@/components/features/conversations/BranchCreationDialog", () => ({
  BranchCreationDialog: ({
    messageId,
    open,
  }: {
    messageId: string | null;
    open: boolean;
  }) => (open ? <div>Branch dialog {messageId}</div> : null),
}));

vi.mock("@/components/features/conversations/MergeSheet", () => ({
  MergeSheet: ({
    branch,
    open,
  }: {
    branch: { id: string } | null;
    open: boolean;
  }) => (open ? <div>Merge sheet {branch?.id}</div> : null),
}));

describe("ConversationView", () => {
  beforeEach(() => {
    getStreamingContentSpy.mockReset();
    messageListSpy.mockReset();
    messagesResult.messages = getConversationFixtures().interactionMessages["interaction-1"] ?? [];
    useConversationStore.getState().reset();
  });

  it("renders the active interaction flow and opens branch and merge controls", async () => {
    const fixtures = getConversationFixtures();
    const conversation = fixtures.conversations[0];
    const user = userEvent.setup();

    if (!conversation) {
      throw new Error("Expected conversation fixture");
    }

    useConversationStore.setState({
      ...useConversationStore.getState(),
      activeBranchId: "branch-1",
      activeInteractionId: "interaction-1",
      isAgentProcessing: true,
    });

    render(<ConversationView conversation={conversation} />);

    expect(screen.getByText("Status for interaction-1 processing")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Open branch merge panel" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Input for conversation-1/interaction-1")).toBeInTheDocument();

    await user.click(screen.getByText("Branch from visible message"));
    expect(screen.getByText("Branch dialog message-1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Open branch merge panel" }));
    expect(screen.getByText("Merge sheet branch-1")).toBeInTheDocument();

    await user.click(screen.getByText("Change interaction"));
    expect(useConversationStore.getState().activeInteractionId).toBe("interaction-2");
    expect(messageListSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        messages: messagesResult.messages,
      }),
    );
  });

  it("omits status and input when there is no active interaction", () => {
    render(
      <ConversationView
        conversation={{
          id: "conversation-empty",
          workspace_id: "workspace-1",
          title: "Empty conversation",
          created_at: "2026-04-12T10:00:00.000Z",
          interactions: [],
          branches: [],
        }}
      />,
    );

    expect(screen.queryByText(/Status for/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Input for/)).not.toBeInTheDocument();
  });
});
