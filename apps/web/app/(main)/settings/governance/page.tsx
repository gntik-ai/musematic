"use client";

import { EmptyState } from "@/components/shared/EmptyState";
import { GovernanceChainEditor } from "@/components/features/governance/governance-chain-editor";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function SettingsGovernancePage() {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);

  if (!workspaceId) {
    return <EmptyState title="Workspace required" description="Select a workspace before editing governance." />;
  }

  return <GovernanceChainEditor scope={{ kind: "workspace", workspaceId }} />;
}
