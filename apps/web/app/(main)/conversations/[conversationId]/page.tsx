"use client";

import { useEffect } from "react";
import { useParams } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { ConversationView } from "@/components/features/conversations/ConversationView";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { EmptyState } from "@/components/shared/EmptyState";
import { useConversation } from "@/lib/hooks/use-conversation";
import { useConversationWs } from "@/lib/hooks/use-conversation-ws";
import { useConversationStore } from "@/lib/stores/conversation-store";

export default function ConversationPage() {
  const params = useParams<{ conversationId: string }>();
  const conversationId = params.conversationId;
  const hydrateFromConversation = useConversationStore(
    (state) => state.hydrateFromConversation,
  );
  const resetConversationStore = useConversationStore((state) => state.reset);

  const conversationQuery = useConversation(conversationId);
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

  return (
    <section className="space-y-4">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          Live thread
        </p>
        <h2 className="mt-2 text-2xl font-semibold">
          {conversationQuery.data.title}
        </h2>
      </div>
      <ConversationView conversation={conversationQuery.data} />
    </section>
  );
}
