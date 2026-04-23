"use client";

import { useEffect } from "react";
import { useParams } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { PerInteractionMuteToggle } from "@/components/features/alerts/per-interaction-mute-toggle";
import { ConversationView } from "@/components/features/conversations/ConversationView";
import { GoalScopedMessageFilter } from "@/components/features/conversations/goal-scoped-message-filter";
import { WorkspaceGoalHeader } from "@/components/features/conversations/workspace-goal-header";
import { EmptyState } from "@/components/shared/EmptyState";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useConversation } from "@/lib/hooks/use-conversation";
import { useGoalLifecycle } from "@/lib/hooks/use-goal-lifecycle";
import { useConversationWs } from "@/lib/hooks/use-conversation-ws";
import { useConversationStore } from "@/lib/stores/conversation-store";

export default function ConversationPage() {
  const params = useParams<{ conversationId: string }>();
  const conversationId = params.conversationId;
  const hydrateFromConversation = useConversationStore(
    (state) => state.hydrateFromConversation,
  );
  const resetConversationStore = useConversationStore((state) => state.reset);
  const selectedGoalId = useConversationStore((state) => state.selectedGoalId);
  const setSelectedGoal = useConversationStore((state) => state.setSelectedGoal);
  const activeInteractionId = useConversationStore(
    (state) => state.activeInteractionId,
  );

  const conversationQuery = useConversation(conversationId);
  const goalLifecycleQuery = useGoalLifecycle(
    conversationQuery.data?.workspace_id ?? null,
  );
  useConversationWs(conversationId);

  useEffect(() => {
    const conversation = conversationQuery.data;
    if (!conversation) {
      return;
    }

    hydrateFromConversation(
      conversation.interactions[0]?.id ?? null,
      conversation.branches,
    );
  }, [conversationQuery.data, hydrateFromConversation]);

  useEffect(() => () => {
    resetConversationStore();
  }, [resetConversationStore]);

  useEffect(() => {
    if (selectedGoalId || !goalLifecycleQuery.activeGoal) {
      return;
    }

    setSelectedGoal(goalLifecycleQuery.activeGoal.id);
  }, [goalLifecycleQuery.activeGoal, selectedGoalId, setSelectedGoal]);

  if (conversationQuery.isLoading) {
    return null;
  }

  if (conversationQuery.error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Conversation unavailable</AlertTitle>
        <AlertDescription>
          The conversation could not be loaded.
        </AlertDescription>
      </Alert>
    );
  }

  if (!conversationQuery.data) {
    return (
      <EmptyState
        description="The requested conversation does not exist."
        title="Conversation not found"
      />
    );
  }

  const currentInteractionId =
    activeInteractionId ?? conversationQuery.data.interactions[0]?.id ?? null;

  return (
    <section className="space-y-4">
      <WorkspaceGoalHeader workspaceId={conversationQuery.data.workspace_id} />
      <GoalScopedMessageFilter
        activeGoalId={selectedGoalId ?? goalLifecycleQuery.activeGoal?.id ?? null}
        workspaceId={conversationQuery.data.workspace_id}
      />
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
            Live thread
          </p>
          <h2 className="mt-2 text-2xl font-semibold">
            {conversationQuery.data.title}
          </h2>
        </div>
        {currentInteractionId ? (
          <PerInteractionMuteToggle interactionId={currentInteractionId} />
        ) : null}
      </div>
      <ConversationView
        activeGoalId={selectedGoalId ?? goalLifecycleQuery.activeGoal?.id ?? null}
        conversation={conversationQuery.data}
      />
    </section>
  );
}
