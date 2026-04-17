import { beforeEach, describe, expect, it } from "vitest";
import { useConversationStore } from "@/lib/stores/conversation-store";
import type { ConversationBranch } from "@/types/conversations";

const branchFixture: ConversationBranch = {
  id: "branch-1",
  conversation_id: "conversation-1",
  name: "Alternative path",
  description: "Explore a different direction",
  originating_message_id: "message-2",
  status: "active",
  created_at: "2026-04-12T10:00:00.000Z",
};

describe("conversation-store", () => {
  beforeEach(() => {
    useConversationStore.getState().reset();
  });

  it("tracks unread state for branches and interactions without duplicating entries", () => {
    const store = useConversationStore.getState();

    store.setActiveInteraction("interaction-1");
    store.markInteractionUnread("interaction-1");
    expect(useConversationStore.getState().unreadInteractionIds).toEqual([]);

    store.markInteractionUnread("interaction-2");
    store.markInteractionUnread("interaction-2");
    expect(useConversationStore.getState().unreadInteractionIds).toEqual(["interaction-2"]);

    store.clearInteractionUnread("interaction-2");
    expect(useConversationStore.getState().unreadInteractionIds).toEqual([]);

    store.setActiveBranch("branch-1");
    store.markBranchUnread("branch-1");
    expect(useConversationStore.getState().unreadBranchIds).toEqual([]);

    store.markBranchUnread("branch-2");
    store.markBranchUnread("branch-2");
    expect(useConversationStore.getState().unreadBranchIds).toEqual(["branch-2"]);

    store.clearBranchUnread("branch-2");
    expect(useConversationStore.getState().unreadBranchIds).toEqual([]);
  });

  it("hydrates branch tabs, avoids duplicates, and updates active selections", () => {
    const store = useConversationStore.getState();

    store.hydrateFromConversation("interaction-1", [branchFixture]);
    expect(useConversationStore.getState().activeInteractionId).toBe("interaction-1");
    expect(useConversationStore.getState().branchTabs).toEqual([
      { id: "branch-1", interactionId: null, name: "Alternative path" },
    ]);

    store.addBranchTab(branchFixture);
    expect(useConversationStore.getState().branchTabs).toHaveLength(1);

    store.setActiveBranch("branch-1");
    store.setActiveInteraction("interaction-2");
    expect(useConversationStore.getState().activeBranchId).toBe("branch-1");
    expect(useConversationStore.getState().activeInteractionId).toBe("interaction-2");
  });

  it("manages pending outbound messages, retry state, and reset", () => {
    const store = useConversationStore.getState();

    store.setAgentProcessing(true, "interaction-1");
    store.pauseAutoScroll();
    store.incrementPending();
    store.setGoalPanelOpen(true);
    store.setSelectedGoal("goal-1");
    store.setRealtimeConnectionDegraded(true);
    store.queueOutboundMessage({
      id: "optimistic-1",
      content: "Queued message",
      conversationId: "conversation-1",
      interactionId: "interaction-1",
      isMidProcessInjection: false,
    });
    store.queueOutboundMessage({
      id: "optimistic-1",
      content: "Queued message",
      conversationId: "conversation-1",
      interactionId: "interaction-1",
      isMidProcessInjection: false,
    });

    expect(useConversationStore.getState().pendingOutboundMessages).toEqual([
      expect.objectContaining({
        id: "optimistic-1",
        retrying: false,
      }),
    ]);

    store.markOutboundMessageRetrying("optimistic-1", true);
    expect(useConversationStore.getState().pendingOutboundMessages[0]?.retrying).toBe(true);

    store.removeOutboundMessage("optimistic-1");
    expect(useConversationStore.getState().pendingOutboundMessages).toEqual([]);

    store.enableAutoScroll();
    store.clearPending();
    store.reset();

    expect(useConversationStore.getState()).toMatchObject({
      activeBranchId: null,
      activeInteractionId: null,
      autoScrollEnabled: true,
      branchTabs: [],
      goalPanelOpen: false,
      isAgentProcessing: false,
      pendingMessageCount: 0,
      pendingOutboundMessages: [],
      realtimeConnectionDegraded: false,
      selectedGoalId: null,
    });
  });
});
