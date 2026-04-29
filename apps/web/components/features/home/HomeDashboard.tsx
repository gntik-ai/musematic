"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LayoutDashboard, Waves } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorBoundary } from "@/components/features/home/ErrorBoundary";
import { ConnectionStatusBanner } from "@/components/features/home/ConnectionStatusBanner";
import { PendingActions } from "@/components/features/home/PendingActions";
import { QuickActions } from "@/components/features/home/QuickActions";
import { RecentActivity } from "@/components/features/home/RecentActivity";
import { SectionError } from "@/components/features/home/SectionError";
import { WorkspaceSummary } from "@/components/features/home/WorkspaceSummary";
import { EmptyState } from "@/components/shared/EmptyState";
import {
  useDashboardWebSocket,
  useWebSocketStatus,
} from "@/lib/hooks/use-home-data";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export function HomeDashboard() {
  const workspace = useWorkspaceStore((state) => state.currentWorkspace);
  const userWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = workspace?.id ?? userWorkspaceId;
  const workspaceName = workspace?.name ?? (workspaceId ? "Current workspace" : null);
  const { isConnected } = useWebSocketStatus();
  const [showRecoveryPrompt, setShowRecoveryPrompt] = useState(false);

  useDashboardWebSocket(workspaceId);

  useEffect(() => {
    setShowRecoveryPrompt(
      new URLSearchParams(window.location.search).get("oauth_recovery") === "1",
    );
  }, []);

  if (!workspaceId) {
    return (
      <EmptyState
        description={[
          "Choose a workspace to load summary metrics, recent activity,",
          "and pending actions.",
        ].join(" ")}
        icon={Waves}
        title="Select a workspace"
      />
    );
  }

  return (
    <div className="space-y-6">
      <ConnectionStatusBanner isConnected={isConnected} />
      {showRecoveryPrompt ? (
        <div className="flex flex-col gap-3 rounded-lg border border-brand-primary/25 bg-brand-primary/10 p-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-sm font-semibold">Access recovered with a linked provider</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              You can request a local password reset now or continue with OAuth sign-in.
            </p>
          </div>
          <div className="flex gap-2">
            <Button asChild size="sm">
              <Link href="/forgot-password">Set local password</Link>
            </Button>
            <Button
              size="sm"
              type="button"
              variant="outline"
              onClick={() => setShowRecoveryPrompt(false)}
            >
              Dismiss
            </Button>
          </div>
        </div>
      ) : null}
      <section className="space-y-2">
        <div
          className={[
            "flex items-center gap-2 text-sm font-semibold uppercase",
            "tracking-[0.2em] text-brand-accent",
          ].join(" ")}
        >
          <LayoutDashboard className="h-4 w-4" />
          Home
        </div>
        <div>
          <h1 className="text-3xl font-semibold">
            {workspaceName} overview
          </h1>
          <p className="mt-2 max-w-3xl text-muted-foreground">
            Monitor live workspace health, approvals, and recent activity from
            one surface.
          </p>
        </div>
      </section>

      <QuickActions />

      <ErrorBoundary
        fallback={<SectionError title="Workspace summary unavailable" />}
        resetKey={workspaceId}
      >
        <WorkspaceSummary isConnected={isConnected} workspaceId={workspaceId} />
      </ErrorBoundary>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ErrorBoundary
          fallback={<SectionError title="Recent activity unavailable" />}
          resetKey={`${workspaceId}-activity`}
        >
          <RecentActivity isConnected={isConnected} workspaceId={workspaceId} />
        </ErrorBoundary>

        <ErrorBoundary
          fallback={<SectionError title="Pending actions unavailable" />}
          resetKey={`${workspaceId}-pending`}
        >
          <PendingActions isConnected={isConnected} workspaceId={workspaceId} />
        </ErrorBoundary>
      </div>
    </div>
  );
}
