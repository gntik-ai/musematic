"use client";

import { use, useMemo } from "react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentIdentityForm } from "@/components/features/agents/agent-identity-form";
import {
  type AgentFormValues,
} from "@/components/features/agents/agent-form-identity-fields";
import { useAgent } from "@/lib/hooks/use-agents";
import { useWorkspaceStore } from "@/store/workspace-store";

function toInitialValues(agent: NonNullable<ReturnType<typeof useAgent>["data"]>): AgentFormValues {
  return {
    namespace: agent.namespace ?? "",
    localName: agent.local_name ?? "",
    purpose: agent.purpose ?? "",
    approach: agent.approach ?? "",
    roleType: (agent.role_type as AgentFormValues["roleType"]) ?? "operator",
    visibilityPatterns: agent.visibility_patterns.map((pattern) => pattern.pattern),
  };
}

export default function EditAgentPage({
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
        <Skeleton className="h-[560px] w-full rounded-3xl" />
      </div>
    );
  }

  if (!agentQuery.data) {
    return (
      <EmptyState
        description="The requested agent could not be loaded for editing."
        title="Agent unavailable"
      />
    );
  }

  return (
    <section className="space-y-6">
      <AgentIdentityForm
        agentId={agentId}
        description="Update FQN identity, purpose, role, and visibility without leaving the new agents route tree."
        initialValues={toInitialValues(agentQuery.data)}
        isLegacy={!agentQuery.data.namespace || !agentQuery.data.local_name}
        mode="edit"
        title="Edit Agent Identity"
      />
    </section>
  );
}
