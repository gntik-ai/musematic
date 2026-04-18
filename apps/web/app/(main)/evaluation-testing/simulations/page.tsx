"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Orbit } from "lucide-react";
import { SimulationRunDataTable } from "@/components/features/simulations/SimulationRunDataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { useSimulationMutations } from "@/lib/hooks/use-simulation-mutations";
import { useSimulationRuns } from "@/lib/hooks/use-simulation-runs";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function SimulationsPage() {
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const runsQuery = useSimulationRuns(workspaceId ?? "", cursor);
  const { createComparison } = useSimulationMutations();

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing simulations."
        icon={Orbit}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Simulations</h1>
        <p className="text-sm text-muted-foreground md:text-base">
          Launch and compare digital twin simulations from one operational surface.
        </p>
      </div>
      <SimulationRunDataTable
        isLoading={runsQuery.isLoading}
        nextCursor={runsQuery.data?.next_cursor ?? null}
        onCompare={async ([primary, secondary]) => {
          const report = await createComparison.mutateAsync({
            primaryRunId: primary,
            secondaryRunId: secondary,
            comparisonType: "simulation_vs_simulation",
          });
          router.push(
            `/evaluation-testing/simulations/compare?primary=${encodeURIComponent(primary)}&secondary=${encodeURIComponent(secondary)}&report=${encodeURIComponent(report.report_id)}&type=simulation_vs_simulation`,
          );
        }}
        onCreate={() => router.push("/evaluation-testing/simulations/new")}
        onLoadMore={() => setCursor(runsQuery.data?.next_cursor ?? undefined)}
        onRowClick={(runId) =>
          router.push(`/evaluation-testing/simulations/${encodeURIComponent(runId)}`)
        }
        onSelectionChange={setSelectedRunIds}
        runs={runsQuery.data?.items ?? []}
        selectedRunIds={selectedRunIds}
      />
    </section>
  );
}
