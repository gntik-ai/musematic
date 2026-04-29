"use client";

import { Bot } from "lucide-react";
import { AgentDataTable } from "@/components/features/agent-management/AgentDataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function AgentsPage() {
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing agents."
        icon={Bot}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Agents</h1>
        <p className="text-sm text-muted-foreground md:text-base">
          Browse visible agents across the current workspace.
        </p>
      </header>
      <AgentDataTable workspace_id={workspaceId} />
    </section>
  );
}
