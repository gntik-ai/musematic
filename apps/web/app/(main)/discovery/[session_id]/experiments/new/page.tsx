"use client";

import { use, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { FlaskConical } from "lucide-react";
import { ExperimentLauncherForm } from "@/components/features/discovery/ExperimentLauncherForm";
import { SessionTabs } from "@/components/features/discovery/SessionTabs";
import { EmptyState } from "@/components/shared/EmptyState";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface NewDiscoveryExperimentPageProps {
  params: Promise<{ session_id: string }>;
}

export default function NewDiscoveryExperimentPage({
  params,
}: NewDiscoveryExperimentPageProps) {
  const { session_id } = use(params);
  const searchParams = useSearchParams();
  const hypothesisId = useMemo(() => searchParams.get("hypothesis") ?? "", [searchParams]);
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;

  if (!workspaceId || !hypothesisId) {
    return (
      <EmptyState
        description="Choose a hypothesis before launching an experiment."
        icon={FlaskConical}
        title="Hypothesis required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Launch experiment</h1>
        <SessionTabs active="experiments" sessionId={session_id} />
      </div>
      <ExperimentLauncherForm hypothesisId={hypothesisId} workspaceId={workspaceId} />
    </section>
  );
}
