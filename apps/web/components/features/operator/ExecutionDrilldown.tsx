"use client";

import { useState } from "react";
import { ArrowLeft, Workflow } from "lucide-react";
import { ActiveExecutionStatusBadge } from "@/components/features/operator/ActiveExecutionStatusBadge";
import { BudgetConsumptionPanel } from "@/components/features/operator/BudgetConsumptionPanel";
import { ContextQualityPanel } from "@/components/features/operator/ContextQualityPanel";
import { ReasoningTracePanel } from "@/components/features/operator/ReasoningTracePanel";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useBudgetStatus,
  useContextQuality,
  useExecutionDetail,
  useReasoningTrace,
} from "@/lib/hooks/use-execution-drill-down";

export interface ExecutionDrilldownProps {
  executionId: string;
}

type DrilldownTab =
  | "reasoning-trace"
  | "context-quality"
  | "budget-consumption";

export function ExecutionDrilldown({ executionId }: ExecutionDrilldownProps) {
  const [activeTab, setActiveTab] = useState<DrilldownTab>("reasoning-trace");
  const detailQuery = useExecutionDetail(executionId);
  const isActive =
    detailQuery.data?.status === "running" ||
    detailQuery.data?.status === "paused" ||
    detailQuery.data?.status === "waiting_for_approval" ||
    detailQuery.data?.status === "compensating";
  const traceQuery = useReasoningTrace(executionId);
  const budgetQuery = useBudgetStatus(executionId, Boolean(isActive));
  const contextQuery = useContextQuality(executionId);

  if (
    detailQuery.isLoading ||
    traceQuery.isLoading ||
    budgetQuery.isLoading ||
    contextQuery.isLoading
  ) {
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
                  Diagnostic views for execution {detailQuery.data.id}
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
            <p className="font-medium">{detailQuery.data.workflowName}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {detailQuery.data.agentFqn}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              Elapsed {(detailQuery.data.elapsedMs / 1000).toFixed(0)}s
            </p>
          </div>
        </CardContent>
      </Card>

      <Tabs>
        <TabsList className="flex w-full flex-wrap gap-2 rounded-[1.5rem] bg-muted/60 p-2">
          <TabsTrigger
            aria-pressed={activeTab === "reasoning-trace"}
            className={activeTab === "reasoning-trace" ? "bg-background shadow-sm" : undefined}
            onClick={() => setActiveTab("reasoning-trace")}
          >
            Reasoning Trace
          </TabsTrigger>
          <TabsTrigger
            aria-pressed={activeTab === "context-quality"}
            className={activeTab === "context-quality" ? "bg-background shadow-sm" : undefined}
            onClick={() => setActiveTab("context-quality")}
          >
            Context Quality
          </TabsTrigger>
          <TabsTrigger
            aria-pressed={activeTab === "budget-consumption"}
            className={activeTab === "budget-consumption" ? "bg-background shadow-sm" : undefined}
            onClick={() => setActiveTab("budget-consumption")}
          >
            Budget Consumption
          </TabsTrigger>
        </TabsList>

        {activeTab === "reasoning-trace" ? (
          <TabsContent>
            <ReasoningTracePanel
              isLoading={traceQuery.isLoading}
              trace={traceQuery.data}
            />
          </TabsContent>
        ) : null}
        {activeTab === "context-quality" ? (
          <TabsContent>
            <ContextQualityPanel
              isLoading={contextQuery.isLoading}
              quality={contextQuery.data}
            />
          </TabsContent>
        ) : null}
        {activeTab === "budget-consumption" ? (
          <TabsContent>
            <BudgetConsumptionPanel
              budget={budgetQuery.data}
              isLoading={budgetQuery.isLoading}
            />
          </TabsContent>
        ) : null}
      </Tabs>
    </section>
  );
}
