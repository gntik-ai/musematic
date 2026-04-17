"use client";

import { use } from "react";
import { useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentDetailView } from "@/components/features/agent-management/AgentDetailView";
import { useAgent } from "@/lib/hooks/use-agents";
import { useWorkspaceStore } from "@/store/workspace-store";
import { ApiError } from "@/types/api";

export default function AgentDetailPage({
  params,
}: {
  params: Promise<{ fqn: string }>;
}) {
  const router = useRouter();
  const resolvedParams = use(params);
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const fqn = useMemo(
    () => decodeURIComponent(resolvedParams.fqn),
    [resolvedParams.fqn],
  );
  const agentQuery = useAgent(fqn, { workspaceId });

  useEffect(() => {
    if (agentQuery.error instanceof ApiError && agentQuery.error.status === 404) {
      router.replace("/agent-management");
    }
  }, [agentQuery.error, router]);

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

  return <AgentDetailView agent={agentQuery.data} />;
}
