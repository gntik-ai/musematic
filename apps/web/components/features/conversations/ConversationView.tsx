"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { GitMerge } from "lucide-react";
import { BranchCreationDialog } from "@/components/features/conversations/BranchCreationDialog";
import { DecisionRationalePanel } from "@/components/features/conversations/decision-rationale-panel";
import { InteractionTabs } from "@/components/features/conversations/InteractionTabs";
import { MergeSheet } from "@/components/features/conversations/MergeSheet";
import { MessageInput } from "@/components/features/conversations/MessageInput";
import { MessageList } from "@/components/features/conversations/MessageList";
import { StatusBar } from "@/components/features/conversations/StatusBar";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { useMessageDecisionRationale } from "@/lib/hooks/use-message-decision-rationale";
import { useMessageStream } from "@/lib/hooks/use-message-stream";
import { useMessages } from "@/lib/hooks/use-messages";
import { useGoalMessages } from "@/lib/hooks/use-workspace-goals";
import { useConversationStore } from "@/lib/stores/conversation-store";
import type { Conversation, GoalMessage, Message } from "@/types/conversations";

interface ConversationViewProps {
  conversation: Conversation;
  activeGoalId?: string | null;
}

function mapGoalMessageToConversationMessage(
  conversationId: string,
  fallbackInteractionId: string | null,
  message: GoalMessage,
): Message {
  return {
    id: message.id,
    conversation_id: conversationId,
    interaction_id:
      message.originating_interaction_id ?? fallbackInteractionId ?? "goal-scoped",
    sender_type: message.sender_type,
    sender_id: message.sender_id,
    sender_display_name: message.sender_display_name,
    content: message.content,
    attachments: [],
    status: "complete",
    is_mid_process_injection: false,
    branch_origin: null,
    created_at: message.created_at,
    updated_at: message.created_at,
  };
}

export function ConversationView({
  conversation,
  activeGoalId = null,
}: ConversationViewProps) {
  const searchParams = useSearchParams();
  const activeBranchId = useConversationStore((state) => state.activeBranchId);
  const activeInteractionId = useConversationStore((state) => state.activeInteractionId);
  const isAgentProcessing = useConversationStore((state) => state.isAgentProcessing);
  const setActiveInteraction = useConversationStore((state) => state.setActiveInteraction);
  const { getStreamingContent } = useMessageStream();
  const [branchDialogMessageId, setBranchDialogMessageId] = useState<string | null>(null);
  const [mergeSheetOpen, setMergeSheetOpen] = useState(false);
  const [debugMessage, setDebugMessage] = useState<Message | null>(null);

  const currentInteraction =
    conversation.interactions.find((interaction) => interaction.id === activeInteractionId) ??
    conversation.interactions[0] ??
    null;

  const activeBranch =
    conversation.branches.find((branch) => branch.id === activeBranchId) ?? null;
  const activeTabId = activeBranch
    ? `conversation-branch-tab-${activeBranch.id}`
    : currentInteraction
      ? `conversation-interaction-tab-${currentInteraction.id}`
      : undefined;

  const messageQuery = useMessages({
    branchId: activeBranchId,
    conversationId: conversation.id,
    interactionId: currentInteraction?.id ?? null,
  });
  const isGoalScopedView =
    searchParams.get("goal-scoped") === "true" &&
    Boolean(activeGoalId) &&
    activeBranchId === null;
  const goalMessagesQuery = useGoalMessages(
    conversation.workspace_id,
    isGoalScopedView ? activeGoalId : null,
  );

  const branchOriginMessageIds = useMemo(
    () => new Set(conversation.branches.map((branch) => branch.originating_message_id)),
    [conversation.branches],
  );
  const visibleMessages = useMemo(() => {
    if (!isGoalScopedView) {
      return messageQuery.messages;
    }

    return goalMessagesQuery.messages.map((message) =>
      mapGoalMessageToConversationMessage(
        conversation.id,
        currentInteraction?.id ?? null,
        message,
      ),
    );
  }, [
    conversation.id,
    currentInteraction?.id,
    goalMessagesQuery.messages,
    isGoalScopedView,
    messageQuery.messages,
  ]);
  const rationaleGoalId = isGoalScopedView
    ? activeGoalId
    : (currentInteraction?.goal_id ?? null);
  const rationaleQuery = useMessageDecisionRationale(
    conversation.workspace_id,
    rationaleGoalId,
    debugMessage?.id ?? null,
  );

  return (
    <div className="space-y-4">
      <InteractionTabs
        conversation={conversation}
        onInteractionChange={setActiveInteraction}
      />
      <div
        aria-labelledby={activeTabId}
        className="space-y-4"
        id="conversation-panel"
        role="tabpanel"
      >
        {currentInteraction ? (
          <StatusBar
            interaction={currentInteraction}
            isProcessing={isAgentProcessing}
          />
        ) : null}
        {isGoalScopedView ? (
          <div className="rounded-2xl border border-border/70 bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
            Goal-scoped view is active. The list below shows only the messages
            linked to the selected workspace goal.
          </div>
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
          branchOriginMessageIds={
            isGoalScopedView ? new Set<string>() : branchOriginMessageIds
          }
          getStreamingContent={getStreamingContent}
          messages={visibleMessages}
          onBranchFromMessage={(messageId) => setBranchDialogMessageId(messageId)}
          onInspectMessage={(message) => setDebugMessage(message)}
        />
        {currentInteraction && !isGoalScopedView ? (
          <MessageInput
            conversationId={conversation.id}
            interactionId={currentInteraction.id}
            isAgentProcessing={isAgentProcessing}
          />
        ) : null}
        {isGoalScopedView ? (
          <p className="text-sm text-muted-foreground">
            Use the workspace goal feed to add guidance while the transcript is
            filtered to goal-linked activity.
          </p>
        ) : null}
      </div>
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
      <Sheet
        onOpenChange={(open) => {
          if (!open) {
            setDebugMessage(null);
          }
        }}
        open={debugMessage !== null}
      >
        <SheetContent className="ml-auto max-w-2xl">
          <SheetTitle>Decision Rationale</SheetTitle>
          <SheetDescription>
            {debugMessage
              ? `Inspect why ${debugMessage.sender_display_name} produced this response.`
              : "Inspect the reasoning behind this agent response."}
          </SheetDescription>
          <div className="mt-6 space-y-4">
            {debugMessage ? (
              <div className="rounded-2xl border border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
                <p className="font-semibold text-foreground">
                  {debugMessage.sender_display_name}
                </p>
                <p className="mt-2 line-clamp-4">{debugMessage.content}</p>
              </div>
            ) : null}
            {rationaleQuery.isLoading ? (
              <div className="rounded-2xl border border-border/70 bg-muted/20 p-4 text-sm text-muted-foreground">
                Loading rationale…
              </div>
            ) : (
              <DecisionRationalePanel rationale={rationaleQuery.rationale} />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
