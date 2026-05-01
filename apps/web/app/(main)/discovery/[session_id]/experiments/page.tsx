"use client";

import Link from "next/link";
import { use } from "react";
import { FlaskConical } from "lucide-react";
import { SessionTabs } from "@/components/features/discovery/SessionTabs";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { useDiscoveryExperiments } from "@/lib/hooks/use-discovery-session";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface DiscoveryExperimentsPageProps {
  params: Promise<{ session_id: string }>;
}

export default function DiscoveryExperimentsPage({ params }: DiscoveryExperimentsPageProps) {
  const { session_id } = use(params);
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const experimentsQuery = useDiscoveryExperiments(session_id, workspaceId);

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Experiments</h1>
          <SessionTabs active="experiments" sessionId={session_id} />
        </div>
        <Button asChild>
          <Link href={`/discovery/${encodeURIComponent(session_id)}/hypotheses`}>
            Choose Hypothesis
          </Link>
        </Button>
      </div>
      {experimentsQuery.data?.items.length ? (
        <div className="grid gap-3">
          {experimentsQuery.data.items.map((experiment) => (
            <article className="rounded-lg border border-border bg-card p-4" key={experiment.experiment_id}>
              <h2 className="font-semibold">{experiment.experiment_id}</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                {experiment.execution_status} / {experiment.governance_status}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          description="No session-level experiment list endpoint is available yet. Launch from a hypothesis to create one."
          icon={FlaskConical}
          title="No experiments listed"
        />
      )}
    </section>
  );
}
