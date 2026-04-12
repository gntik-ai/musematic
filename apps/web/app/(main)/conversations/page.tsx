"use client";

import Link from "next/link";
import { MessagesSquare } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { createApiClient } from "@/lib/api";
import { queryKeys, type Conversation, type ConversationListResponse } from "@/types/conversations";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

const api = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

export default function ConversationsPage() {
  const currentWorkspace = useWorkspaceStore((state) => state.currentWorkspace);
  const userWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspace?.id ?? userWorkspaceId;

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.conversationList(workspaceId ?? "no-workspace"),
    queryFn: () =>
      api.get<ConversationListResponse>(
        `/api/v1/conversations?workspace_id=${workspaceId ?? ""}`,
      ),
    enabled: Boolean(workspaceId),
  });

  const conversations = data?.items ?? [];

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace to load active conversations."
        icon={MessagesSquare}
        title="Choose a workspace"
      />
    );
  }

  if (!isLoading && conversations.length === 0) {
    return (
      <EmptyState
        ctaLabel="Start a conversation"
        description="No conversations exist in this workspace yet."
        icon={MessagesSquare}
        onCtaClick={() => {
          window.location.assign("/conversations/new");
        }}
        title="No conversations yet"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm text-muted-foreground">
          Browse recent workstreams and jump back into any interaction thread.
        </p>
      </div>
      <div className="grid gap-4">
        {isLoading
          ? Array.from({ length: 3 }, (_, index) => (
              <Card key={`conversation-skeleton-${index}`} className="animate-pulse">
                <CardHeader>
                  <div className="h-5 w-48 rounded bg-muted" />
                  <div className="h-4 w-72 rounded bg-muted" />
                </CardHeader>
              </Card>
            ))
          : conversations.map((conversation) => (
              <ConversationCard
                conversation={conversation}
                key={conversation.id}
              />
            ))}
      </div>
    </div>
  );
}

function ConversationCard({ conversation }: { conversation: Conversation }) {
  return (
    <Link className="block" href={`/conversations/${conversation.id}`}>
      <Card className="transition-colors hover:border-brand-accent/40 hover:bg-accent/20">
        <CardHeader>
          <CardTitle>{conversation.title}</CardTitle>
          <CardDescription>
            {conversation.interactions.length} interaction
            {conversation.interactions.length === 1 ? "" : "s"} ·{" "}
            {conversation.branches.length} branch
            {conversation.branches.length === 1 ? "" : "es"}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4 text-sm text-muted-foreground">
          <span className="truncate">
            Workspace: {conversation.workspace_id}
          </span>
          <span className="shrink-0">
            Started {new Date(conversation.created_at).toLocaleDateString()}
          </span>
        </CardContent>
      </Card>
    </Link>
  );
}
