"use client";

import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useConversationStore } from "@/lib/stores/conversation-store";
import type { Conversation } from "@/types/conversations";

interface InteractionTabsProps {
  conversation: Conversation;
  onInteractionChange: (interactionId: string) => void;
}

export function InteractionTabs({
  conversation,
  onInteractionChange,
}: InteractionTabsProps) {
  const activeBranchId = useConversationStore((state) => state.activeBranchId);
  const activeInteractionId = useConversationStore((state) => state.activeInteractionId);
  const branchTabs = useConversationStore((state) => state.branchTabs);
  const clearBranchUnread = useConversationStore((state) => state.clearBranchUnread);
  const clearInteractionUnread = useConversationStore((state) => state.clearInteractionUnread);
  const setActiveBranch = useConversationStore((state) => state.setActiveBranch);
  const setActiveInteraction = useConversationStore((state) => state.setActiveInteraction);
  const unreadBranchIds = useConversationStore((state) => state.unreadBranchIds);
  const unreadInteractionIds = useConversationStore((state) => state.unreadInteractionIds);

  return (
    <Tabs>
      <TabsList
        className="flex w-full flex-wrap gap-2 overflow-x-auto bg-transparent p-0"
        role="tablist"
      >
        {conversation.interactions.map((interaction) => {
          const isActive =
            activeBranchId === null && activeInteractionId === interaction.id;
          const hasUnreadMessages = unreadInteractionIds.includes(interaction.id);

          return (
            <TabsTrigger
              aria-selected={isActive}
              className={`border ${isActive ? "border-brand-accent bg-accent" : "border-border bg-muted/40"}`}
              key={interaction.id}
              onClick={() => {
                setActiveBranch(null);
                setActiveInteraction(interaction.id);
                clearInteractionUnread(interaction.id);
                onInteractionChange(interaction.id);
              }}
              role="tab"
            >
              <span className="truncate">{interaction.agent_display_name}</span>
              {hasUnreadMessages ? (
                <span className="ml-2 inline-flex h-2.5 w-2.5 rounded-full bg-brand-accent" />
              ) : null}
            </TabsTrigger>
          );
        })}
        {branchTabs.map((branch) => {
          const isActive = activeBranchId === branch.id;
          const hasUnreadMessages = unreadBranchIds.includes(branch.id);

          return (
            <TabsTrigger
              aria-selected={isActive}
              className={`border italic ${isActive ? "border-brand-accent bg-accent" : "border-border bg-muted/40"}`}
              key={branch.id}
              onClick={() => {
                setActiveBranch(branch.id);
                clearBranchUnread(branch.id);
              }}
              role="tab"
            >
              <span className="max-w-36 truncate">{branch.name}</span>
              {hasUnreadMessages ? (
                <span className="ml-2 inline-flex h-2.5 w-2.5 rounded-full bg-brand-accent" />
              ) : null}
            </TabsTrigger>
          );
        })}
      </TabsList>
      {activeBranchId ? (
        <div className="mt-3">
          <Button size="sm" variant="outline">
            Active branch
          </Button>
        </div>
      ) : null}
    </Tabs>
  );
}
