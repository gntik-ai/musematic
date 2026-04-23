"use client";

import { EmptyState } from "@/components/shared/EmptyState";
import { VisibilityGrantsEditor } from "@/components/features/governance/visibility-grants-editor";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function SettingsVisibilityPage() {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);

  if (!workspaceId) {
    return <EmptyState title="Workspace required" description="Select a workspace before editing visibility grants." />;
  }

  return <VisibilityGrantsEditor workspaceId={workspaceId} />;
}
