"use client";

import { use, useMemo, useState } from "react";
import { Lightbulb } from "lucide-react";
import { HypothesisCard, confidenceTier } from "@/components/features/discovery/HypothesisCard";
import { SessionTabs } from "@/components/features/discovery/SessionTabs";
import {
  HypothesisFilterBar,
  type HypothesisFilterState,
} from "@/components/features/discovery/HypothesisFilterBar";
import { HypothesisDetailPanel } from "@/components/features/discovery/HypothesisDetailPanel";
import { EmptyState } from "@/components/shared/EmptyState";
import { useDiscoveryHypotheses } from "@/lib/hooks/use-discovery-session";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface DiscoveryHypothesesPageProps {
  params: Promise<{ session_id: string }>;
}

export default function DiscoveryHypothesesPage({ params }: DiscoveryHypothesesPageProps) {
  const { session_id } = use(params);
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const [filters, setFilters] = useState<HypothesisFilterState>({
    state: "",
    confidence: "",
    sort: "elo_desc",
  });
  const hypothesesQuery = useDiscoveryHypotheses({
    sessionId: session_id,
    workspaceId,
    status: filters.state || null,
    orderBy: filters.sort,
  });
  const filtered = useMemo(
    () =>
      (hypothesesQuery.data?.items ?? []).filter(
        (item) => !filters.confidence || confidenceTier(item.confidence).startsWith(filters.confidence),
      ),
    [filters.confidence, hypothesesQuery.data?.items],
  );
  const selected = filtered[0] ?? null;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing hypotheses."
        icon={Lightbulb}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Hypotheses</h1>
        <SessionTabs active="hypotheses" sessionId={session_id} />
      </div>
      <HypothesisFilterBar value={filters} onChange={setFilters} />
      {filtered.length === 0 ? (
        <EmptyState
          description="No hypotheses match the current filters."
          icon={Lightbulb}
          title="No hypotheses"
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1fr,24rem]">
          <div className="grid gap-3">
            {filtered.map((hypothesis) => (
              <HypothesisCard
                href={`/discovery/${encodeURIComponent(session_id)}/evidence/${encodeURIComponent(hypothesis.hypothesis_id)}`}
                hypothesis={hypothesis}
                key={hypothesis.hypothesis_id}
              />
            ))}
          </div>
          {selected ? (
            <HypothesisDetailPanel hypothesis={selected} workspaceId={workspaceId} />
          ) : null}
        </div>
      )}
    </section>
  );
}
