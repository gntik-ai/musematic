"use client";

import { use } from "react";
import Link from "next/link";
import { Workflow } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { WorkflowEditorShell } from "@/components/features/workflows/editor/WorkflowEditorShell";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkflow } from "@/lib/hooks/use-workflow";

interface WorkflowEditorMonitorDetailPageProps {
  params: Promise<{
    id: string;
  }>;
}

function WorkflowEditorSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-10 w-48" />
      <Skeleton className="h-24 rounded-3xl" />
      <Skeleton className="h-[720px] rounded-3xl" />
    </div>
  );
}

export default function WorkflowEditorMonitorDetailPage({
  params,
}: WorkflowEditorMonitorDetailPageProps) {
  const { id: workflowId } = use(params);
  const workflowQuery = useWorkflow(workflowId);

  if (workflowQuery.isLoading) {
    return <WorkflowEditorSkeleton />;
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
      <div className="space-y-2">
        <Link
          className="inline-flex text-sm font-medium text-brand-primary transition hover:text-brand-primary/80"
          href="/workflow-editor-monitor"
        >
          Back to workflows
        </Link>
        <div>
          <h1 className="text-3xl font-semibold">
            {workflowQuery.data.workflow.name}
          </h1>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            Edit the YAML definition, inspect the compiled graph, and publish a
            new workflow version when you are ready.
          </p>
        </div>
      </div>

      <WorkflowEditorShell
        compiledIr={workflowQuery.data.version.compiledIr}
        initialVersionId={workflowQuery.data.version.id}
        initialYamlContent={workflowQuery.data.version.yamlContent}
        versionNumber={workflowQuery.data.version.versionNumber}
        workflowId={workflowId}
      />
    </div>
  );
}
