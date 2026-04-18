"use client";

import { useMemo, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { JsonViewer } from "@/components/shared/JsonViewer";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { useSimulationMutations } from "@/lib/hooks/use-simulation-mutations";
import type {
  ComparisonType,
  DigitalTwinResponse,
  SimulationRunResponse,
} from "@/types/simulation";

export interface SimulationDetailViewProps {
  run: SimulationRunResponse;
  twins: DigitalTwinResponse[];
  onComparisonCreated?: ((reportId: string, type: ComparisonType) => void) | undefined;
}

function statusClasses(status: SimulationRunResponse["status"]): string {
  switch (status) {
    case "completed":
      return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
    case "failed":
    case "timeout":
      return "bg-destructive/10 text-foreground";
    case "cancelled":
      return "text-muted-foreground";
    case "running":
      return "bg-sky-500/15 text-sky-700 dark:text-sky-300";
    case "provisioning":
    default:
      return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
  }
}

export function SimulationDetailView({
  run,
  twins,
  onComparisonCreated,
}: SimulationDetailViewProps) {
  const { cancelRun, createComparison } = useSimulationMutations();
  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false);
  const [comparePopoverOpen, setComparePopoverOpen] = useState(false);
  const [customRange, setCustomRange] = useState({ from: "", to: "" });

  const selectedTwins = useMemo(
    () => twins.filter((twin) => run.digital_twin_ids.includes(twin.twin_id)),
    [run.digital_twin_ids, twins],
  );

  const createProductionComparison = async (period: Record<string, unknown>) => {
    const report = await createComparison.mutateAsync({
      primaryRunId: run.run_id,
      productionBaselinePeriod: period,
      comparisonType: "simulation_vs_production",
    });
    setComparePopoverOpen(false);
    onComparisonCreated?.(report.report_id, "simulation_vs_production");
  };

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <Badge className="bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200" variant="outline">
              SIMULATION
            </Badge>
            <Badge
              aria-busy={
                run.status === "provisioning" || run.status === "running"
                  ? "true"
                  : undefined
              }
              className={statusClasses(run.status)}
              variant="secondary"
            >
              {run.status}
            </Badge>
          </div>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">{run.name}</h1>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
              {run.description ?? "Simulation execution detail and digital twin context."}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {run.status === "provisioning" || run.status === "running" ? (
            <Button variant="destructive" onClick={() => setConfirmCancelOpen(true)}>
              Cancel
            </Button>
          ) : null}
          <Popover open={comparePopoverOpen} onOpenChange={setComparePopoverOpen}>
            <PopoverTrigger asChild>
              <Button>Compare with Production</Button>
            </PopoverTrigger>
            <PopoverContent className="w-80 space-y-3">
              <div className="space-y-2">
                <p className="text-sm font-medium">Baseline period</p>
                <div className="grid grid-cols-3 gap-2">
                  <Button variant="outline" onClick={() => createProductionComparison({ preset: "last_7_days" })}>
                    Last 7 days
                  </Button>
                  <Button variant="outline" onClick={() => createProductionComparison({ preset: "last_30_days" })}>
                    Last 30 days
                  </Button>
                  <Button variant="outline" onClick={() => createProductionComparison({ preset: "last_90_days" })}>
                    Last 90 days
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Custom range</p>
                <Input
                  type="date"
                  value={customRange.from}
                  onChange={(event) =>
                    setCustomRange((current) => ({ ...current, from: event.target.value }))
                  }
                />
                <Input
                  type="date"
                  value={customRange.to}
                  onChange={(event) =>
                    setCustomRange((current) => ({ ...current, to: event.target.value }))
                  }
                />
                <Button
                  className="w-full"
                  disabled={!customRange.from || !customRange.to}
                  onClick={() =>
                    createProductionComparison({
                      from: customRange.from,
                      to: customRange.to,
                    })
                  }
                >
                  Compare custom range
                </Button>
              </div>
            </PopoverContent>
          </Popover>
          <Button disabled variant="outline">
            Compare with Other Simulation
          </Button>
        </div>
      </div>

      {run.status === "timeout" ? (
        <Alert className="border-amber-500/30 bg-amber-500/10 text-foreground">
          <AlertTitle>Simulation timed out</AlertTitle>
          <AlertDescription>
            Simulation timed out. Try re-running with a shorter duration.
          </AlertDescription>
        </Alert>
      ) : null}

      {run.status === "completed" && run.results ? (
        <JsonViewer maxDepth={2} value={run.results} />
      ) : null}

      <div className="space-y-3 rounded-2xl border border-border/70 bg-card/80 p-4">
        <div>
          <h2 className="text-lg font-semibold">Digital twins</h2>
          <p className="text-sm text-muted-foreground">
            Review the source agents, versions, and warning flags used in this run.
          </p>
        </div>
        {selectedTwins.map((twin) => (
          <details className="rounded-xl border border-border/60 p-4" key={twin.twin_id}>
            <summary className="cursor-pointer list-none font-medium">
              {twin.source_agent_fqn} v{twin.version}
            </summary>
            <div className="mt-3 space-y-3 text-sm">
              <p>Modifications: {twin.modifications.length}</p>
              <div className="flex flex-wrap gap-2">
                {twin.warning_flags.length > 0 ? (
                  twin.warning_flags.map((flag) => (
                    <Badge
                      className="border-amber-500/30 bg-amber-500/10 text-foreground"
                      key={flag}
                      variant="outline"
                    >
                      {flag}
                    </Badge>
                  ))
                ) : (
                  <Badge variant="outline">No warnings</Badge>
                )}
              </div>
            </div>
          </details>
        ))}
      </div>

      <ConfirmDialog
        confirmLabel="Cancel simulation"
        description="Cancel this simulation? This cannot be undone."
        isLoading={cancelRun.isPending}
        onConfirm={async () => {
          await cancelRun.mutateAsync(run.run_id);
          setConfirmCancelOpen(false);
        }}
        onOpenChange={setConfirmCancelOpen}
        open={confirmCancelOpen}
        title="Cancel simulation"
        variant="destructive"
      />
    </section>
  );
}
