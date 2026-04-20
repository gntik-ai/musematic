"use client";

import { use, useMemo } from "react";
import Link from "next/link";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { AgentDetailView } from "@/components/features/agent-management/AgentDetailView";
import { useAgent } from "@/lib/hooks/use-agents";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function AgentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolvedParams = use(params);
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const agentId = useMemo(() => decodeURIComponent(resolvedParams.id), [resolvedParams.id]);
  const agentQuery = useAgent(agentId, { workspaceId });

  if (agentQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16 w-full rounded-3xl" />
        <Skeleton className="h-96 w-full rounded-3xl" />
      </div>
    );
  }

  if (!agentQuery.data) {
    return (
      <EmptyState
        description="The requested agent could not be loaded."
        title="Agent unavailable"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          className="inline-flex text-sm font-medium text-brand-primary transition hover:text-brand-primary/80"
          href="/agents"
        >
          Back to agents
        </Link>
        <Button asChild variant="outline">
          <Link href={`/agents/${encodeURIComponent(agentId)}/edit`}>Edit identity</Link>
        </Button>
      </div>
      <AgentDetailView agent={agentQuery.data} />
    </div>
  );
}
