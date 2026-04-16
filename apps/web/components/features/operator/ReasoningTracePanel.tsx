"use client";

import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ReasoningTraceStep } from "@/components/features/operator/ReasoningTraceStep";
import type { ReasoningTrace } from "@/lib/types/operator-dashboard";

export interface ReasoningTracePanelProps {
  trace: ReasoningTrace | undefined;
  isLoading: boolean;
}

export function ReasoningTracePanel({
  trace,
  isLoading,
}: ReasoningTracePanelProps) {
  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Reasoning trace</CardTitle>
        <p className="text-sm text-muted-foreground">
          Ordered diagnostic steps and self-correction loops captured for this
          execution.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-20 rounded-xl" />
          ))
        ) : !trace ? (
          <EmptyState
            description="No reasoning steps recorded"
            title="Reasoning trace unavailable"
          />
        ) : trace.steps.length === 0 ? (
          <EmptyState
            description="No reasoning steps recorded"
            title="Reasoning trace empty"
          />
        ) : (
          <>
            <div className="rounded-xl border border-border/60 bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
              {trace.totalTokens} tokens · {trace.totalDurationMs}ms ·{" "}
              {trace.totalCorrectionIterations} corrections
            </div>
            <div className="space-y-3">
              {trace.steps.map((step, index) => (
                <ReasoningTraceStep
                  key={step.id}
                  step={step}
                  stepNumber={index + 1}
                />
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
