"use client";

import { PauseCircle, PlayCircle, Scaling, ShieldEllipsis } from "lucide-react";
import { useMemo, useState } from "react";
import { ScaleDialog } from "@/components/features/fleet/ScaleDialog";
import { StressTestDialog } from "@/components/features/fleet/StressTestDialog";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Badge } from "@/components/ui/badge";
import { usePauseFleet, useResumeFleet } from "@/lib/hooks/use-fleet-actions";
import {
  useFleetGovernance,
  useFleetOrchestration,
  useFleetPersonality,
} from "@/lib/hooks/use-fleet-governance";
import type { FleetMember, FleetStatus } from "@/lib/types/fleet";

interface FleetControlsPanelProps {
  fleetId: string;
  currentStatus: FleetStatus;
  members?: FleetMember[];
}

export function FleetControlsPanel({
  fleetId,
  currentStatus,
  members = [],
}: FleetControlsPanelProps) {
  const pauseFleetMutation = usePauseFleet();
  const resumeFleetMutation = useResumeFleet();
  const governanceQuery = useFleetGovernance(fleetId);
  const orchestrationQuery = useFleetOrchestration(fleetId);
  const personalityQuery = useFleetPersonality(fleetId);
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false);
  const [resumeDialogOpen, setResumeDialogOpen] = useState(false);
  const [scaleDialogOpen, setScaleDialogOpen] = useState(false);
  const [stressDialogOpen, setStressDialogOpen] = useState(false);
  const [stressTestRunning, setStressTestRunning] = useState(false);

  const transitionLabel = useMemo(() => {
    if (pauseFleetMutation.isPending) {
      return "Transitioning to paused state…";
    }
    if (resumeFleetMutation.isPending) {
      return "Resuming fleet operations…";
    }
    return null;
  }, [pauseFleetMutation.isPending, resumeFleetMutation.isPending]);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {(currentStatus === "active" || currentStatus === "degraded") ? (
          <button
            aria-label="Pause fleet"
            className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 text-left shadow-sm transition-colors hover:bg-card"
            type="button"
            onClick={() => setPauseDialogOpen(true)}
          >
            <PauseCircle className="h-5 w-5 text-brand-accent" />
            <p className="mt-4 text-lg font-semibold">Pause</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Drain current work and block new execution starts.
            </p>
          </button>
        ) : null}

        {currentStatus === "paused" ? (
          <button
            aria-label="Resume fleet"
            className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 text-left shadow-sm transition-colors hover:bg-card"
            type="button"
            onClick={() => setResumeDialogOpen(true)}
          >
            <PlayCircle className="h-5 w-5 text-brand-accent" />
            <p className="mt-4 text-lg font-semibold">Resume</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Return the fleet to active routing and scheduling.
            </p>
          </button>
        ) : null}

        <button
          aria-label="Scale fleet"
          className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 text-left shadow-sm transition-colors hover:bg-card"
          type="button"
          onClick={() => setScaleDialogOpen(true)}
        >
          <Scaling className="h-5 w-5 text-brand-accent" />
          <p className="mt-4 text-lg font-semibold">Scale</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Expand the fleet by adding compatible worker agents.
          </p>
        </button>

        <button
          aria-label="Stress test fleet"
          className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 text-left shadow-sm transition-colors hover:bg-card disabled:cursor-not-allowed disabled:opacity-60"
          disabled={stressTestRunning}
          title={stressTestRunning ? "A stress test is already running." : undefined}
          type="button"
          onClick={() => setStressDialogOpen(true)}
        >
          <ShieldEllipsis className="h-5 w-5 text-brand-accent" />
          <p className="mt-4 text-lg font-semibold">Stress test</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Simulate sustained load with live execution telemetry.
          </p>
        </button>
      </div>

      {transitionLabel ? (
        <Badge className="border-brand-accent/40 bg-brand-accent/10 text-foreground" variant="outline">
          {transitionLabel}
        </Badge>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <section className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm">
          <h3 className="font-semibold">Governance</h3>
          <p className="mt-3 text-sm text-muted-foreground">
            {(governanceQuery.data?.observer_fqns.length ?? 0)} observers · {(governanceQuery.data?.judge_fqns.length ?? 0)} judges
          </p>
        </section>
        <section className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm">
          <h3 className="font-semibold">Orchestration</h3>
          <p className="mt-3 text-sm text-muted-foreground">
            Max parallelism {orchestrationQuery.data?.max_parallelism ?? "n/a"} · version {orchestrationQuery.data?.version ?? "n/a"}
          </p>
        </section>
        <section className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm">
          <h3 className="font-semibold">Personality</h3>
          <p className="mt-3 text-sm text-muted-foreground capitalize">
            {(personalityQuery.data?.communication_style ?? "n/a").replaceAll("_", " ")} · {(personalityQuery.data?.autonomy_level ?? "n/a").replaceAll("_", " ")}
          </p>
        </section>
      </div>

      <ConfirmDialog
        confirmLabel="Pause fleet"
        description="Pause the fleet after draining current work? Any active execution count returned by the API will be surfaced after confirmation."
        isLoading={pauseFleetMutation.isPending}
        open={pauseDialogOpen}
        title="Pause fleet"
        onConfirm={() => {
          void pauseFleetMutation.mutateAsync({ fleetId }).then(() => setPauseDialogOpen(false));
        }}
        onOpenChange={setPauseDialogOpen}
      />

      <ConfirmDialog
        confirmLabel="Resume fleet"
        description="Resume fleet execution and accept new work?"
        isLoading={resumeFleetMutation.isPending}
        open={resumeDialogOpen}
        title="Resume fleet"
        onConfirm={() => {
          void resumeFleetMutation.mutateAsync({ fleetId }).then(() => setResumeDialogOpen(false));
        }}
        onOpenChange={setResumeDialogOpen}
      />

      <ScaleDialog
        currentMemberCount={members.length}
        existingMemberFqns={members.map((member) => member.agent_fqn)}
        fleetId={fleetId}
        open={scaleDialogOpen}
        onOpenChange={setScaleDialogOpen}
      />

      <StressTestDialog
        fleetId={fleetId}
        open={stressDialogOpen}
        onOpenChange={setStressDialogOpen}
        onRunStateChange={setStressTestRunning}
      />
    </div>
  );
}
