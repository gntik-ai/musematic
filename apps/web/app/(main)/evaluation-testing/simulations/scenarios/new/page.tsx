"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Library } from "lucide-react";
import { SimulationScenarioEditor } from "@/components/features/simulations/SimulationScenarioEditor";
import { EmptyState } from "@/components/shared/EmptyState";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function NewSimulationScenarioPage() {
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before creating a scenario."
        icon={Library}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <Link
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          href="/evaluation-testing/simulations/scenarios"
        >
          Back to scenarios
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">New scenario</h1>
      </div>
      <SimulationScenarioEditor
        mode="create"
        workspaceId={workspaceId}
        onSaved={(scenario) =>
          router.push(`/evaluation-testing/simulations/scenarios/${encodeURIComponent(scenario.id)}`)
        }
      />
    </section>
  );
}
