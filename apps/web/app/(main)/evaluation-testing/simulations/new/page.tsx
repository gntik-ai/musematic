"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Orbit } from "lucide-react";
import { CreateSimulationForm } from "@/components/features/simulations/CreateSimulationForm";
import { EmptyState } from "@/components/shared/EmptyState";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function CreateSimulationPage() {
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before creating a simulation."
        icon={Orbit}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <Link
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          href="/evaluation-testing/simulations"
        >
          Back to Simulations
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Create Simulation</h1>
      </div>
      <CreateSimulationForm
        workspaceId={workspaceId}
        onSuccess={(runId) =>
          router.push(`/evaluation-testing/simulations/${encodeURIComponent(runId)}`)
        }
      />
    </section>
  );
}
