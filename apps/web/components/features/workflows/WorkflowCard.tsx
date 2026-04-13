"use client";

import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { WorkflowDefinition, WorkflowStatus } from "@/types/workflows";

const workflowStatusStyles: Record<
  WorkflowStatus,
  { label: string; className: string; variant: "default" | "secondary" | "outline" }
> = {
  active: {
    label: "Active",
    className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
    variant: "outline",
  },
  draft: {
    label: "Draft",
    className: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
    variant: "outline",
  },
  archived: {
    label: "Archived",
    className: "text-muted-foreground",
    variant: "outline",
  },
};

function WorkflowStatusBadge({ status }: { status: WorkflowStatus }) {
  const config = workflowStatusStyles[status];

  return (
    <Badge className={config.className} variant={config.variant}>
      {config.label}
    </Badge>
  );
}

export function WorkflowCard({ workflow }: { workflow: WorkflowDefinition }) {
  return (
    <Card className="h-full border-border/60 transition-colors hover:border-brand-accent/40 hover:bg-accent/10">
      <CardHeader className="gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <CardTitle className="text-xl">{workflow.name}</CardTitle>
            <CardDescription>
              {workflow.description ?? "No description yet."}
            </CardDescription>
          </div>
          <WorkflowStatusBadge status={workflow.status} />
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="outline">Version {workflow.currentVersionNumber}</Badge>
          <span>
            Updated{" "}
            {formatDistanceToNow(new Date(workflow.updatedAt), {
              addSuffix: true,
            })}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
          <div>
            <span className="font-medium text-foreground">Created:</span>{" "}
            {formatDistanceToNow(new Date(workflow.createdAt), {
              addSuffix: true,
            })}
          </div>
          <div>
            <span className="font-medium text-foreground">Workflow ID:</span>{" "}
            {workflow.id}
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button asChild size="sm">
            <Link href={`/workflow-editor-monitor/${workflow.id}`}>Edit</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link href={`/workflow-editor-monitor/${workflow.id}/executions`}>
              View Executions
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
