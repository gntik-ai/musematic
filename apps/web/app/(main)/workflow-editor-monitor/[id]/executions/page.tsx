"use client";

import { use } from "react";
import Link from "next/link";
import { formatDistanceStrict, formatDistanceToNow } from "date-fns";
import { Play, Rows3, Workflow } from "lucide-react";
import { useRouter } from "next/navigation";
import { EmptyState } from "@/components/shared/EmptyState";
import { ExecutionStatusBadge } from "@/components/features/workflows/ExecutionStatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useExecutionList,
  useStartExecution,
} from "@/lib/hooks/use-execution-list";
import { useWorkflow } from "@/lib/hooks/use-workflow";
import type { Execution } from "@/types/execution";

interface WorkflowExecutionListPageProps {
  params: Promise<{
    id: string;
  }>;
}

function ExecutionHistorySkeleton() {
  return (
    <div className="rounded-xl border border-border/60 bg-card/90 p-6 shadow-sm">
      <div className="space-y-3">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-full" />
      </div>
      <div className="mt-6 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-24" />
      </div>
      <div className="mt-6">
        <Skeleton className="h-9 w-32 rounded-md" />
      </div>
    </div>
  );
}

function formatExecutionDuration(execution: Execution) {
  if (!execution.completedAt) {
    return "In progress";
  }

  return formatDistanceStrict(
    new Date(execution.startedAt),
    new Date(execution.completedAt),
  );
}

function ExecutionHistoryCard({
  execution,
  workflowId,
}: {
  execution: Execution;
  workflowId: string;
}) {
  return (
    <Card className="border-border/60 transition-colors hover:border-brand-accent/40 hover:bg-accent/10">
      <CardHeader className="gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <CardTitle className="text-xl">{execution.id}</CardTitle>
            <CardDescription>
              Triggered by {execution.triggeredBy}
            </CardDescription>
          </div>
          <ExecutionStatusBadge status={execution.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2 xl:grid-cols-4">
          <div>
            <span className="font-medium text-foreground">Started:</span>{" "}
            {formatDistanceToNow(new Date(execution.startedAt), {
              addSuffix: true,
            })}
          </div>
          <div>
            <span className="font-medium text-foreground">Duration:</span>{" "}
            {formatExecutionDuration(execution)}
          </div>
          <div>
            <span className="font-medium text-foreground">Version:</span>{" "}
            {execution.workflowVersionNumber}
          </div>
          <div>
            <span className="font-medium text-foreground">Execution:</span>{" "}
            {execution.workflowVersionId}
          </div>
        </div>
        <Button asChild size="sm" variant="outline">
          <Link href={`/workflow-editor-monitor/${workflowId}/executions/${execution.id}`}>
            View Monitor
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export default function WorkflowExecutionListPage({
  params,
}: WorkflowExecutionListPageProps) {
  const router = useRouter();
  const { id: workflowId } = use(params);
  const workflowQuery = useWorkflow(workflowId);
  const executionListQuery = useExecutionList(workflowId);
  const startExecution = useStartExecution(workflowId);

  const executions = executionListQuery.data?.pages.flatMap((page) => page.items) ?? [];

  if (workflowQuery.isLoading) {
    return (
      <div className="space-y-4">
        <ExecutionHistorySkeleton />
        <ExecutionHistorySkeleton />
      </div>
    );
  }

  if (workflowQuery.isError || !workflowQuery.data) {
    return (
      <EmptyState
        description="The requested workflow could not be loaded."
        icon={Workflow}
        title="Workflow unavailable"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <Link
            className="inline-flex text-sm font-medium text-brand-primary transition hover:text-brand-primary/80"
            href={`/workflow-editor-monitor/${workflowId}`}
          >
            Back to workflow
          </Link>
          <div>
            <h1 className="text-3xl font-semibold">
              {workflowQuery.data.workflow.name} executions
            </h1>
            <p className="mt-2 max-w-2xl text-muted-foreground">
              Review past runs, inspect status, and launch a fresh execution for
              the current workflow version.
            </p>
          </div>
        </div>
        <Button
          className="shrink-0"
          disabled={startExecution.isPending}
          disabledByMaintenance
          onClick={async () => {
            const execution = await startExecution.mutateAsync({
              workflowVersionId: workflowQuery.data.version.id,
            });
            router.push(
              `/workflow-editor-monitor/${workflowId}/executions/${execution.id}`,
            );
          }}
        >
          <Play className="h-4 w-4" />
          {startExecution.isPending ? "Starting..." : "Start New Execution"}
        </Button>
      </div>

      {executionListQuery.isLoading ? (
        <div className="space-y-4">
          <ExecutionHistorySkeleton />
          <ExecutionHistorySkeleton />
        </div>
      ) : executions.length === 0 ? (
        <EmptyState
          ctaButtonProps={{ disabledByMaintenance: true }}
          ctaLabel="Start execution"
          description="No executions have run for this workflow yet."
          icon={Rows3}
          onCtaClick={() => {
            void startExecution
              .mutateAsync({
                workflowVersionId: workflowQuery.data.version.id,
              })
              .then((execution) => {
                router.push(
                  `/workflow-editor-monitor/${workflowId}/executions/${execution.id}`,
                );
              });
          }}
          title="No executions yet"
        />
      ) : (
        <div className="space-y-4">
          {executions.map((execution) => (
            <ExecutionHistoryCard
              execution={execution}
              key={execution.id}
              workflowId={workflowId}
            />
          ))}

          {executionListQuery.hasNextPage ? (
            <div className="flex justify-center pt-2">
              <Button
                disabled={executionListQuery.isFetchingNextPage}
                onClick={() => {
                  void executionListQuery.fetchNextPage();
                }}
                variant="outline"
              >
                {executionListQuery.isFetchingNextPage
                  ? "Loading more..."
                  : "Load more executions"}
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
