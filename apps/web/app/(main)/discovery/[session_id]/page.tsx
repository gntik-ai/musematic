"use client";

import { use } from "react";
import { SearchCheck } from "lucide-react";
import { SessionTabs } from "@/components/features/discovery/SessionTabs";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import {
  useDiscoveryExperiments,
  useDiscoveryHypotheses,
  useDiscoverySession,
} from "@/lib/hooks/use-discovery-session";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface DiscoverySessionPageProps {
  params: Promise<{ session_id: string }>;
}

export default function DiscoverySessionPage({ params }: DiscoverySessionPageProps) {
  const { session_id } = use(params);
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const sessionQuery = useDiscoverySession(session_id, workspaceId);
  const hypothesesQuery = useDiscoveryHypotheses({ sessionId: session_id, workspaceId });
  const experimentsQuery = useDiscoveryExperiments(session_id, workspaceId);

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before opening discovery sessions."
        icon={SearchCheck}
        title="Workspace required"
      />
    );
  }

  const session = sessionQuery.data;

  return (
    <section className="space-y-6">
      <div className="space-y-4">
        <Badge variant="outline">{session?.status ?? "loading"}</Badge>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Discovery session</h1>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
            {session?.research_question ?? "Loading research question."}
          </p>
        </div>
        <SessionTabs sessionId={session_id} active="overview" />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Metric label="Cycle" value={session?.current_cycle ?? 0} />
        <Metric label="Hypotheses" value={hypothesesQuery.data?.items.length ?? 0} />
        <Metric label="Experiments" value={experimentsQuery.data?.items.length ?? 0} />
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
    </div>
  );
}
