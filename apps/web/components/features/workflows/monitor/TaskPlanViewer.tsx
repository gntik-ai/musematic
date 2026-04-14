"use client";

import { Network, Sparkles } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import type { TaskPlanCandidate, TaskPlanRecord } from "@/types/task-plan";

function CandidateRow({ candidate }: { candidate: TaskPlanCandidate }) {
  return (
    <div className="rounded-xl border border-border/60 bg-background/80 p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium text-foreground">{candidate.displayName}</p>
          <p className="text-sm text-muted-foreground">{candidate.fqn}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={candidate.isSelected ? "default" : "outline"}>
            {candidate.isSelected ? "Selected" : "Candidate"}
          </Badge>
          <Badge variant="outline">
            {(candidate.suitabilityScore * 100).toFixed(0)}%
          </Badge>
        </div>
      </div>
      <div className="mt-3 h-2 rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-brand-primary"
          style={{ width: `${candidate.suitabilityScore * 100}%` }}
        />
      </div>
      {candidate.tags.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {candidate.tags.map((tag) => (
            <Badge key={`${candidate.fqn}-${tag}`} variant="outline">
              {tag}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function TaskPlanViewer({
  isLoading,
  taskPlan,
}: {
  isLoading?: boolean;
  taskPlan: TaskPlanRecord | null | undefined;
}) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-40 rounded-xl" />
      </div>
    );
  }

  if (!taskPlan) {
    return (
      <EmptyState
        description="This step was not dispatched to an agent, so no task plan was stored."
        icon={Network}
        title="No task plan available"
      />
    );
  }

  return (
    <div className="space-y-4">
      <Alert className="border-border/70 bg-card/80">
        <Sparkles className="h-4 w-4" />
        <AlertTitle>Selected agent</AlertTitle>
        <AlertDescription>
          <span className="font-medium text-foreground">
            {taskPlan.selectedAgentFqn ?? taskPlan.selectedToolFqn ?? "Not available"}
          </span>
          <span className="block pt-1">{taskPlan.rationaleText}</span>
        </AlertDescription>
      </Alert>

      <Collapsible defaultOpen>
        <CollapsibleTrigger className="text-left text-sm font-medium text-foreground">
          Candidates
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3 space-y-3">
            {taskPlan.candidateAgents.map((candidate) => (
              <CandidateRow candidate={candidate} key={candidate.fqn} />
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>

      <Collapsible defaultOpen>
        <CollapsibleTrigger className="text-left text-sm font-medium text-foreground">
          Parameters
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3 space-y-3">
            {taskPlan.parameters.map((parameter) => (
              <div
                className="rounded-xl border border-border/60 bg-background/80 p-3"
                key={parameter.parameterName}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium text-foreground">
                    {parameter.parameterName}
                  </p>
                  <Badge variant="outline">{parameter.source}</Badge>
                </div>
                <code className="mt-3 block overflow-x-auto rounded-lg bg-muted/60 px-3 py-2 text-xs text-foreground">
                  {JSON.stringify(parameter.value)}
                </code>
                <p className="mt-2 text-sm text-muted-foreground">
                  {parameter.sourceDescription}
                </p>
              </div>
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>

      <Collapsible>
        <CollapsibleTrigger className="text-left text-sm font-medium text-foreground">
          Rejected alternatives
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="mt-3 space-y-3">
            {taskPlan.rejectedAlternatives.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No rejected alternatives were recorded.
              </p>
            ) : (
              taskPlan.rejectedAlternatives.map((alternative) => (
                <div
                  className="rounded-xl border border-border/60 bg-background/80 p-3"
                  key={alternative.fqn}
                >
                  <p className="font-medium text-foreground">{alternative.fqn}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {alternative.rejectionReason}
                  </p>
                </div>
              ))
            )}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
