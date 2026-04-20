"use client";

import { useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Workflow } from "lucide-react";
import { CheckpointList } from "@/components/features/execution/checkpoint-list";
import { DebateTranscript } from "@/components/features/execution/debate-transcript";
import { ReactCycleViewer } from "@/components/features/execution/react-cycle-viewer";
import { TrajectoryViz } from "@/components/features/execution/trajectory-viz";
import { ActiveExecutionStatusBadge } from "@/components/features/operator/ActiveExecutionStatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useExecutionDetail } from "@/lib/hooks/use-execution-drill-down";

export interface ExecutionDrilldownProps {
  executionId: string;
}

type DrilldownTab = "trajectory" | "checkpoints" | "debate" | "react";

const VALID_TABS = new Set<DrilldownTab>([
  "trajectory",
  "checkpoints",
  "debate",
  "react",
]);

function resolveTab(value: string | null): DrilldownTab {
  return value && VALID_TABS.has(value as DrilldownTab)
    ? (value as DrilldownTab)
    : "trajectory";
}

function parseAnchorStep(value: string | null): number | undefined {
  if (!value) {
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return undefined;
  }
  return Math.floor(parsed);
}

export function ExecutionDrilldown({ executionId }: ExecutionDrilldownProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const detailQuery = useExecutionDetail(executionId);

  const activeTab = resolveTab(searchParams.get("tab"));
  const anchorStepIndex = parseAnchorStep(searchParams.get("step"));

  const updateTab = (tab: DrilldownTab) => {
    const params = new URLSearchParams(searchParams.toString());
    if (tab === "trajectory") {
      params.delete("tab");
    } else {
      params.set("tab", tab);
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname);
  };

  const diagnosticSummary = useMemo(() => {
    if (!detailQuery.data) {
      return null;
    }

    return {
      workflowName: detailQuery.data.workflowName,
      agentFqn: detailQuery.data.agentFqn,
      elapsedSeconds: (detailQuery.data.elapsedMs / 1000).toFixed(0),
    };
  }, [detailQuery.data]);

  if (detailQuery.isLoading) {
    return (
      <section className="space-y-6">
        <Skeleton className="h-12 w-40 rounded-xl" />
        <Skeleton className="h-24 rounded-[2rem]" />
        <Skeleton className="h-[640px] rounded-[2rem]" />
      </section>
    );
  }

  if (!detailQuery.data) {
    return (
      <EmptyState
        description="Execution drill-down data could not be loaded."
        title="Execution unavailable"
      />
    );
  }

  return (
    <section className="space-y-6">
      <div>
        <Button asChild variant="outline">
          <a href="/operator">
            <ArrowLeft className="h-4 w-4" />
            Operator
          </a>
        </Button>
      </div>

      <Card className="overflow-hidden rounded-[2rem] bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.18),transparent_28%),linear-gradient(140deg,hsl(var(--card))_0%,hsl(var(--muted)/0.52)_100%)]">
        <CardContent className="flex flex-col gap-5 p-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-border/60 bg-background/75 p-3">
                <Workflow className="h-5 w-5 text-brand-accent" />
              </div>
              <div>
                <h1 className="text-3xl font-semibold tracking-tight">
                  Execution Drill-Down
                </h1>
                <p className="text-sm text-muted-foreground">
                  Trajectory, checkpoints, debate, and ReAct diagnostics for execution {detailQuery.data.id}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <ActiveExecutionStatusBadge status={detailQuery.data.status} />
              <span className="font-mono text-sm text-muted-foreground">
                {detailQuery.data.id}
              </span>
            </div>
          </div>
          <div className="rounded-[1.75rem] border border-border/60 bg-background/75 p-4 shadow-sm">
            <p className="font-medium">{diagnosticSummary?.workflowName}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {diagnosticSummary?.agentFqn}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Elapsed {diagnosticSummary?.elapsedSeconds}s
            </p>
          </div>
        </CardContent>
      </Card>

      <Tabs>
        <TabsList className="flex w-full flex-wrap gap-2 rounded-[1.5rem] bg-muted/60 p-2">
          <TabsTrigger
            aria-pressed={activeTab === "trajectory"}
            className={activeTab === "trajectory" ? "bg-background shadow-sm" : undefined}
            onClick={() => updateTab("trajectory")}
          >
            Trajectory
          </TabsTrigger>
          <TabsTrigger
            aria-pressed={activeTab === "checkpoints"}
            className={activeTab === "checkpoints" ? "bg-background shadow-sm" : undefined}
            onClick={() => updateTab("checkpoints")}
          >
            Checkpoints
          </TabsTrigger>
          <TabsTrigger
            aria-pressed={activeTab === "debate"}
            className={activeTab === "debate" ? "bg-background shadow-sm" : undefined}
            onClick={() => updateTab("debate")}
          >
            Debate
          </TabsTrigger>
          <TabsTrigger
            aria-pressed={activeTab === "react"}
            className={activeTab === "react" ? "bg-background shadow-sm" : undefined}
            onClick={() => updateTab("react")}
          >
            ReAct
          </TabsTrigger>
        </TabsList>

        {activeTab === "trajectory" ? (
          <TabsContent>
            {anchorStepIndex === undefined ? (
              <TrajectoryViz executionId={executionId} />
            ) : (
              <TrajectoryViz anchorStepIndex={anchorStepIndex} executionId={executionId} />
            )}
          </TabsContent>
        ) : null}
        {activeTab === "checkpoints" ? (
          <TabsContent>
            <CheckpointList executionId={executionId} />
          </TabsContent>
        ) : null}
        {activeTab === "debate" ? (
          <TabsContent>
            <DebateTranscript executionId={executionId} />
          </TabsContent>
        ) : null}
        {activeTab === "react" ? (
          <TabsContent>
            <ReactCycleViewer executionId={executionId} />
          </TabsContent>
        ) : null}
      </Tabs>
    </section>
  );
}
