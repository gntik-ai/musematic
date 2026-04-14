"use client";

import { formatDistanceStrict } from "date-fns";
import { MoreVertical } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ConnectionStatusBanner } from "@/components/features/home/ConnectionStatusBanner";
import { ExecutionStatusBadge } from "@/components/features/workflows/ExecutionStatusBadge";
import { CostTracker } from "@/components/features/workflows/monitor/CostTracker";
import { ExecutionControls } from "@/components/features/workflows/monitor/ExecutionControls";
import { ExecutionGraph } from "@/components/features/workflows/monitor/ExecutionGraph";
import { ExecutionTimeline } from "@/components/features/workflows/monitor/ExecutionTimeline";
import { StepDetailPanel } from "@/components/features/workflows/monitor/StepDetailPanel";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import type { Execution } from "@/types/execution";
import type { WorkflowIR } from "@/types/workflows";

function formatElapsedTime(execution: Execution) {
  const end = execution.completedAt ? new Date(execution.completedAt) : new Date();
  return formatDistanceStrict(new Date(execution.startedAt), end);
}

function getStepProgress(stepStatuses: Record<string, string>) {
  const statuses = Object.values(stepStatuses);
  const total = statuses.length;
  const completed = statuses.filter((status) =>
    ["completed", "skipped", "canceled"].includes(status),
  ).length;

  return { completed, total };
}

type MonitorSection = "graph" | "timeline" | "detail";

export function ExecutionMonitorShell({
  execution,
  compiledIr,
}: {
  execution: Execution;
  compiledIr: WorkflowIR;
}) {
  const executionStatus = useExecutionMonitorStore((state) => state.executionStatus);
  const selectedStepId = useExecutionMonitorStore((state) => state.selectedStepId);
  const stepStatuses = useExecutionMonitorStore((state) => state.stepStatuses);
  const wsConnectionStatus = useExecutionMonitorStore(
    (state) => state.wsConnectionStatus,
  );
  const [mobileSection, setMobileSection] = useState<MonitorSection>("graph");
  const [controlsOpen, setControlsOpen] = useState(false);

  const progress = useMemo(() => getStepProgress(stepStatuses), [stepStatuses]);

  useEffect(() => {
    if (selectedStepId) {
      setMobileSection("detail");
    }
  }, [selectedStepId]);

  return (
    <div className="space-y-4">
      <ConnectionStatusBanner isConnected={wsConnectionStatus === "connected"} />

      <div className="rounded-3xl border border-border/70 bg-card/80 p-5 shadow-sm">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <ExecutionStatusBadge status={executionStatus ?? execution.status} />
              <span className="text-sm text-muted-foreground">
                Started {formatElapsedTime(execution)} ago
              </span>
            </div>
            <div>
              <h1 className="text-3xl font-semibold">Execution monitor</h1>
              <p className="mt-2 max-w-3xl text-muted-foreground">
                Track live step transitions, inspect journal events, and intervene
                when the workflow needs operator action.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3 text-sm">
              <p className="font-medium text-foreground">Progress</p>
              <p className="text-muted-foreground">
                {progress.completed}/{progress.total} steps finished
              </p>
            </div>

            <div className="hidden lg:block">
              <ExecutionControls executionId={execution.id} />
            </div>

            <div className="lg:hidden">
              <Sheet open={controlsOpen} onOpenChange={setControlsOpen}>
                <SheetTrigger asChild>
                  <Button aria-label="Open execution controls" size="icon" variant="outline">
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </SheetTrigger>
                <SheetContent className="max-w-sm">
                  <SheetTitle>Execution controls</SheetTitle>
                  <div className="mt-4">
                    <ExecutionControls executionId={execution.id} />
                  </div>
                </SheetContent>
              </Sheet>
            </div>
          </div>
        </div>
      </div>

      <div className="xl:hidden">
        <Tabs>
          <TabsList className="w-full justify-start overflow-x-auto">
            <TabsTrigger
              className={mobileSection === "graph" ? "bg-background" : ""}
              onClick={() => setMobileSection("graph")}
            >
              Graph
            </TabsTrigger>
            <TabsTrigger
              className={mobileSection === "timeline" ? "bg-background" : ""}
              onClick={() => setMobileSection("timeline")}
            >
              Timeline
            </TabsTrigger>
            <TabsTrigger
              className={mobileSection === "detail" ? "bg-background" : ""}
              onClick={() => setMobileSection("detail")}
            >
              Detail
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="mt-4 space-y-4">
          {mobileSection === "graph" ? (
            <ExecutionGraph compiledIr={compiledIr} />
          ) : null}
          {mobileSection === "timeline" ? (
            <ExecutionTimeline executionId={execution.id} />
          ) : null}
          {mobileSection === "detail" ? (
            selectedStepId ? (
              <StepDetailPanel executionId={execution.id} />
            ) : (
              <div className="rounded-3xl border border-dashed border-border/70 bg-card/50 px-6 py-10 text-center text-sm text-muted-foreground">
                Select a step on the graph to inspect its detail panel.
              </div>
            )
          ) : null}
        </div>
      </div>

      <div className="hidden xl:block">
        <ResizablePanelGroup
          className="min-h-[700px]"
          id="execution-monitor-shell"
          orientation="horizontal"
        >
          <ResizablePanel defaultSize={40} minSize={25}>
            <div className="h-full pr-3">
              <ExecutionGraph compiledIr={compiledIr} />
            </div>
          </ResizablePanel>
          <ResizableHandle />
          <ResizablePanel defaultSize={35} minSize={25}>
            <div className="h-full px-3">
              <ExecutionTimeline executionId={execution.id} />
            </div>
          </ResizablePanel>
          <ResizableHandle />
          <ResizablePanel
            collapsible
            collapsedSize={0}
            defaultSize={selectedStepId ? 25 : 0}
            minSize={20}
          >
            <div className="h-full pl-3">
              {selectedStepId ? (
                <StepDetailPanel executionId={execution.id} />
              ) : (
                <div className="flex h-full items-center justify-center rounded-3xl border border-dashed border-border/70 bg-card/50 px-6 text-center text-sm text-muted-foreground">
                  Select a step on the graph to inspect its detail panel.
                </div>
              )}
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      <div className="sticky bottom-0 z-10">
        <CostTracker executionId={execution.id} />
      </div>
    </div>
  );
}
