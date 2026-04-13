"use client";

import {
  formatDuration,
  formatDistanceToNow,
  intervalToDuration,
} from "date-fns";
import { AlertTriangle, Clock3, PlayCircle } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { JsonViewer } from "@/components/shared/JsonViewer";
import { ScoreGauge } from "@/components/shared/ScoreGauge";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import type { StepDetail } from "@/types/execution";

function formatStepDuration(durationMs: number | null) {
  if (durationMs === null) {
    return "Not available";
  }

  return (
    formatDuration(
      intervalToDuration({
        start: 0,
        end: durationMs,
      }),
    ) || "Less than 1 second"
  );
}

export function StepOverviewTab({
  stepDetail,
  isLoading,
}: {
  stepDetail: StepDetail | null | undefined;
  isLoading?: boolean;
}) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
    );
  }

  if (!stepDetail || stepDetail.startedAt === null) {
    return (
      <EmptyState
        description="This step has not started yet, so no detailed runtime data is available."
        icon={PlayCircle}
        title="Step not started"
      />
    );
  }

  const contextScore = stepDetail.contextQualityScore;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="grid gap-4 rounded-2xl border border-border/70 bg-card/80 p-4 sm:grid-cols-2">
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Started
            </p>
            <p className="text-sm font-medium text-foreground">
              {formatDistanceToNow(new Date(stepDetail.startedAt), {
                addSuffix: true,
              })}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Completed
            </p>
            <p className="text-sm font-medium text-foreground">
              {stepDetail.completedAt
                ? formatDistanceToNow(new Date(stepDetail.completedAt), {
                    addSuffix: true,
                  })
                : "Still running"}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Duration
            </p>
            <p className="text-sm font-medium text-foreground">
              {formatStepDuration(stepDetail.durationMs)}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Status
            </p>
            <p className="text-sm font-medium text-foreground">
              {stepDetail.status}
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-border/70 bg-card/80 p-4">
          {contextScore === null ? (
            <EmptyState
              description="No context quality score was produced for this step."
              icon={Clock3}
              title="No quality score"
            />
          ) : (
            <ScoreGauge
              label="Context quality"
              score={Math.round(contextScore * 100)}
            />
          )}
        </div>
      </div>

      {stepDetail.error ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{stepDetail.error.code}</AlertTitle>
          <AlertDescription>
            {stepDetail.error.message}
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="space-y-3">
        <div>
          <h3 className="text-base font-semibold">Inputs</h3>
          <p className="text-sm text-muted-foreground">
            Runtime payload consumed by this step.
          </p>
        </div>
        <JsonViewer maxDepth={2} value={stepDetail.inputs} />
      </div>

      <div className="space-y-3">
        <div>
          <h3 className="text-base font-semibold">Outputs</h3>
          <p className="text-sm text-muted-foreground">
            Materialized output captured after the step completed.
          </p>
        </div>
        {stepDetail.outputs ? (
          <JsonViewer maxDepth={2} value={stepDetail.outputs} />
        ) : (
          <EmptyState
            description="No output payload has been persisted for this step."
            icon={Clock3}
            title="No outputs yet"
          />
        )}
      </div>
    </div>
  );
}
