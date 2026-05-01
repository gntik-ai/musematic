"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { Library, Play } from "lucide-react";
import { ScenarioRunDialog } from "@/components/features/simulations/ScenarioRunDialog";
import { SimulationScenarioEditor } from "@/components/features/simulations/SimulationScenarioEditor";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { useScenario } from "@/lib/hooks/use-simulation-scenarios";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

interface SimulationScenarioDetailPageProps {
  params: Promise<{ id: string }>;
}

export default function SimulationScenarioDetailPage({
  params,
}: SimulationScenarioDetailPageProps) {
  const { id } = use(params);
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const scenarioQuery = useScenario(id, workspaceId);
  const [launchOpen, setLaunchOpen] = useState(false);

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before editing scenarios."
        icon={Library}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <Link
            className="text-sm text-muted-foreground underline-offset-4 hover:underline"
            href="/evaluation-testing/simulations/scenarios"
          >
            Back to scenarios
          </Link>
          <h1 className="text-3xl font-semibold tracking-tight">
            {scenarioQuery.data?.name ?? "Scenario"}
          </h1>
        </div>
        <Button
          disabled={!scenarioQuery.data || Boolean(scenarioQuery.data.archived_at)}
          disabledByMaintenance
          onClick={() => setLaunchOpen(true)}
        >
          <Play className="h-4 w-4" />
          Launch
        </Button>
      </div>
      <SimulationScenarioEditor
        mode="edit"
        scenarioId={id}
        workspaceId={workspaceId}
      />
      <div className="rounded-lg border border-border/70 bg-card/80 p-4">
        <h2 className="font-semibold">Recent runs</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Runs queued from this scenario appear in the main simulations list.
        </p>
      </div>
      <ScenarioRunDialog
        open={launchOpen}
        scenario={scenarioQuery.data ?? null}
        workspaceId={workspaceId}
        onOpenChange={setLaunchOpen}
        onQueued={(summary) => {
          const firstRun = summary.queued_runs[0];
          if (firstRun) {
            router.push(`/evaluation-testing/simulations/${encodeURIComponent(firstRun)}`);
          }
        }}
      />
    </section>
  );
}
