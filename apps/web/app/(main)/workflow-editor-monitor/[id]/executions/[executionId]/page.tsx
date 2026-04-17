"use client";

import { use } from "react";
import Link from "next/link";
import { useEffect } from "react";
import { Activity } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { ExecutionMonitorShell } from "@/components/features/workflows/monitor/ExecutionMonitorShell";
import { Skeleton } from "@/components/ui/skeleton";
import { useExecutionMonitor } from "@/lib/hooks/use-execution-monitor";
import { useExecution, useExecutionState } from "@/lib/hooks/use-execution-list";
import { useWorkflow } from "@/lib/hooks/use-workflow";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";

interface WorkflowExecutionMonitorPageProps {
  params: Promise<{
    id: string;
    executionId: string;
  }>;
}

function MonitorSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-10 w-56" />
      <Skeleton className="h-28 rounded-3xl" />
      <Skeleton className="h-[760px] rounded-3xl" />
    </div>
  );
}

export default function WorkflowExecutionMonitorPage({
  params,
}: WorkflowExecutionMonitorPageProps) {
  const { executionId, id: workflowId } = use(params);
  const executionQuery = useExecution(executionId);
  const executionStateQuery = useExecutionState(executionId);
  const workflowQuery = useWorkflow(workflowId);
  const resetMonitor = useExecutionMonitorStore((state) => state.reset);
  const setExecutionState = useExecutionMonitorStore((state) => state.setExecutionState);

  useExecutionMonitor(executionId);

  useEffect(() => {
    if (executionStateQuery.data) {
      setExecutionState(executionStateQuery.data);
    }
  }, [executionStateQuery.data, setExecutionState]);

  useEffect(() => {
    return () => {
      resetMonitor();
    };
  }, [resetMonitor]);

  if (
    executionQuery.isLoading ||
    executionStateQuery.isLoading ||
    workflowQuery.isLoading
  ) {
    return <MonitorSkeleton />;
  }

  if (
    executionQuery.isError ||
    executionStateQuery.isError ||
    workflowQuery.isError ||
    !executionQuery.data ||
    !executionStateQuery.data ||
    !workflowQuery.data
  ) {
    return (
      <EmptyState
        description="The requested execution monitor could not be loaded."
        icon={Activity}
        title="Execution unavailable"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          className="inline-flex text-sm font-medium text-brand-primary transition hover:text-brand-primary/80"
          href={`/workflow-editor-monitor/${workflowId}/executions`}
        >
          Back to executions
        </Link>
        <div>
          <h1 className="text-3xl font-semibold">
            {workflowQuery.data.workflow.name} monitor
          </h1>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            Monitor the live execution graph, inspect step detail artifacts, and
            apply operator controls without leaving the page.
          </p>
        </div>
      </div>

      <ExecutionMonitorShell
        compiledIr={workflowQuery.data.version.compiledIr}
        execution={executionQuery.data}
      />
    </div>
  );
}
