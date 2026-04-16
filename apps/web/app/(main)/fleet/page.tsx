"use client";

import { Orbit, Radar, UsersRound } from "lucide-react";
import { FleetDataTable } from "@/components/features/fleet/FleetDataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function FleetPage() {
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing fleets."
        icon={Orbit}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <header className="overflow-hidden rounded-[2rem] border bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.18),transparent_26%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--muted)/0.55)_100%)] p-6 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <Badge className="w-fit bg-background/70 text-foreground" variant="outline">
              Fleet dashboard
            </Badge>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
                Operational fleet overview
              </h1>
              <p className="mt-3 max-w-3xl text-sm text-muted-foreground md:text-base">
                Track topology posture, member counts, and live health across every orchestration fleet in the workspace.
              </p>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-border/60 bg-background/75 p-4 shadow-sm">
              <Orbit className="h-4 w-4 text-brand-accent" />
              <p className="mt-3 text-sm font-medium">Topology-first</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Hierarchical, mesh, and hybrid fleets in one surface.
              </p>
            </div>
            <div className="rounded-2xl border border-border/60 bg-background/75 p-4 shadow-sm">
              <Radar className="h-4 w-4 text-brand-accent" />
              <p className="mt-3 text-sm font-medium">Health-aware</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Color-coded health scores surface degraded fleets immediately.
              </p>
            </div>
            <div className="rounded-2xl border border-border/60 bg-background/75 p-4 shadow-sm">
              <UsersRound className="h-4 w-4 text-brand-accent" />
              <p className="mt-3 text-sm font-medium">Member scale</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Compare quorum, member counts, and operational status at a glance.
              </p>
            </div>
          </div>
        </div>
      </header>

      <FleetDataTable workspace_id={workspaceId} />
    </section>
  );
}
