"use client";

import Link from "next/link";
import { use } from "react";
import { useRouter } from "next/navigation";
import { useSearchParams } from "next/navigation";
import { DigitalTwinPanel } from "@/components/features/simulations/DigitalTwinPanel";
import { SimulationDetailView } from "@/components/features/simulations/SimulationDetailView";
import { useDigitalTwins } from "@/lib/hooks/use-digital-twins";
import { useSimulationRun } from "@/lib/hooks/use-simulation-runs";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface SimulationDetailPageProps {
  params: Promise<{
    runId: string;
  }>;
}

export default function SimulationDetailPage({ params }: SimulationDetailPageProps) {
  const { runId } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const runQuery = useSimulationRun(runId);
  const twinsQuery = useDigitalTwins(workspaceId ?? "");

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <Link
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          href="/evaluation-testing/simulations"
        >
          Back to Simulations
        </Link>
      </div>
      {runQuery.data ? (
        <SimulationDetailView
          onComparisonCreated={(reportId, type) => {
            const base = `/evaluation-testing/simulations/compare?primary=${encodeURIComponent(runQuery.data.run_id)}&report=${encodeURIComponent(reportId)}&type=${encodeURIComponent(type)}`;
            router.push(base);
          }}
          run={runQuery.data}
          twins={twinsQuery.data?.items ?? []}
        />
      ) : (
        <div className="rounded-2xl border border-border/70 bg-card/80 p-6 text-sm text-muted-foreground">
          Loading simulation detail…
        </div>
      )}
      {runQuery.data ? (
        <DigitalTwinPanel
          reportId={searchParams.get("report")}
          runId={runQuery.data.run_id}
        />
      ) : null}
    </section>
  );
}
