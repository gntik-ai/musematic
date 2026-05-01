"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Library, Plus } from "lucide-react";
import { ScenarioLibraryTable } from "@/components/features/simulations/ScenarioLibraryTable";
import { ScenarioRunDialog } from "@/components/features/simulations/ScenarioRunDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import {
  useArchiveScenario,
  useScenarios,
} from "@/lib/hooks/use-simulation-scenarios";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import type { SimulationScenario } from "@/types/simulation";

export default function SimulationScenariosPage() {
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const scenariosQuery = useScenarios(workspaceId ?? "");
  const archiveScenario = useArchiveScenario(workspaceId ?? "");
  const [launchScenario, setLaunchScenario] = useState<SimulationScenario | null>(null);

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing simulation scenarios."
        icon={Library}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Simulation scenarios</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Manage reusable scenario definitions and queue multi-iteration runs.
          </p>
        </div>
        <Button onClick={() => router.push("/evaluation-testing/simulations/scenarios/new")}>
          <Plus className="h-4 w-4" />
          New Scenario
        </Button>
      </div>
      <ScenarioLibraryTable
        isLoading={scenariosQuery.isLoading}
        onArchive={(scenarioId) => {
          void archiveScenario.mutateAsync(scenarioId);
        }}
        onEdit={(scenarioId) =>
          router.push(`/evaluation-testing/simulations/scenarios/${encodeURIComponent(scenarioId)}`)
        }
        onLaunch={setLaunchScenario}
        onOpen={(scenarioId) =>
          router.push(`/evaluation-testing/simulations/scenarios/${encodeURIComponent(scenarioId)}`)
        }
        scenarios={scenariosQuery.data?.items ?? []}
      />
      <ScenarioRunDialog
        open={Boolean(launchScenario)}
        scenario={launchScenario}
        workspaceId={workspaceId}
        onOpenChange={(open) => {
          if (!open) {
            setLaunchScenario(null);
          }
        }}
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
