"use client";

import { useMemo, useState } from "react";
import { GitMerge } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BranchCreationDialog } from "@/components/features/conversations/BranchCreationDialog";
import { InteractionTabs } from "@/components/features/conversations/InteractionTabs";
import { MergeSheet } from "@/components/features/conversations/MergeSheet";
import { MessageInput } from "@/components/features/conversations/MessageInput";
import { MessageList } from "@/components/features/conversations/MessageList";
import { StatusBar } from "@/components/features/conversations/StatusBar";
import { useMessageStream } from "@/lib/hooks/use-message-stream";
import { useMessages } from "@/lib/hooks/use-messages";
import { useConversationStore } from "@/lib/stores/conversation-store";
import type { Conversation } from "@/types/conversations";

interface ConversationViewProps {
  conversation: Conversation;
}

export function ConversationView({
  conversation,
}: ConversationViewProps) {
  const activeBranchId = useConversationStore((state) => state.activeBranchId);
  const activeInteractionId = useConversationStore((state) => state.activeInteractionId);
  const isAgentProcessing = useConversationStore((state) => state.isAgentProcessing);
  const setActiveInteraction = useConversationStore((state) => state.setActiveInteraction);
  const { getStreamingContent } = useMessageStream();
  const [branchDialogMessageId, setBranchDialogMessageId] = useState<string | null>(null);
  const [mergeSheetOpen, setMergeSheetOpen] = useState(false);

  const currentInteraction =
    conversation.interactions.find((interaction) => interaction.id === activeInteractionId) ??
    conversation.interactions[0] ??
    null;

  const activeBranch =
    conversation.branches.find((branch) => branch.id === activeBranchId) ?? null;

  const messageQuery = useMessages({
    branchId: activeBranchId,
    conversationId: conversation.id,
    interactionId: currentInteraction?.id ?? null,
  });

  const branchOriginMessageIds = useMemo(
    () => new Set(conversation.branches.map((branch) => branch.originating_message_id)),
    [conversation.branches],
  );

  return (
    <div className="space-y-4">
      <InteractionTabs
        conversation={conversation}
        onInteractionChange={setActiveInteraction}
      />
      {currentInteraction ? (
        <StatusBar
          interaction={currentInteraction}
          isProcessing={isAgentProcessing}
        />
      ) : null}
      {activeBranch ? (
        <div className="flex justify-end">
          <Button
            aria-label="Open branch merge panel"
            onClick={() => setMergeSheetOpen(true)}
            size="sm"
            variant="outline"
          >
            <GitMerge className="h-4 w-4" />
            Merge branch
          </Button>
        </div>
      ) : null}
      <MessageList
        branchOriginMessageIds={branchOriginMessageIds}
        getStreamingContent={getStreamingContent}
        messages={messageQuery.messages}
        onBranchFromMessage={(messageId) => setBranchDialogMessageId(messageId)}
      />
      {currentInteraction ? (
        <MessageInput
          conversationId={conversation.id}
          interactionId={currentInteraction.id}
          isAgentProcessing={isAgentProcessing}
        />
      ) : null}
      <BranchCreationDialog
        conversationId={conversation.id}
        messageId={branchDialogMessageId}
        onOpenChange={(open) => {
          if (!open) {
            setBranchDialogMessageId(null);
          }
        }}
        open={branchDialogMessageId !== null}
      />
      <MergeSheet
        branch={activeBranch}
        conversationId={conversation.id}
        messages={messageQuery.messages}
        onOpenChange={setMergeSheetOpen}
        open={mergeSheetOpen}
      />
    </div>
  );
}
