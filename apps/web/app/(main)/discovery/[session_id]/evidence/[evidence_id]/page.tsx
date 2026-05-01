"use client";

import { use } from "react";
import { SearchCheck } from "lucide-react";
import { EvidenceInspectorView } from "@/components/features/discovery/EvidenceInspectorView";
import { SessionTabs } from "@/components/features/discovery/SessionTabs";
import { EmptyState } from "@/components/shared/EmptyState";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface DiscoveryEvidencePageProps {
  params: Promise<{ session_id: string; evidence_id: string }>;
}

export default function DiscoveryEvidencePage({ params }: DiscoveryEvidencePageProps) {
  const { session_id, evidence_id } = use(params);
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before inspecting evidence."
        icon={SearchCheck}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Evidence</h1>
        <SessionTabs active="evidence" sessionId={session_id} />
      </div>
      <EvidenceInspectorView hypothesisId={evidence_id} workspaceId={workspaceId} />
    </section>
  );
}
