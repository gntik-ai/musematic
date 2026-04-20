"use client";

import { useEffect, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useExecutionTrajectory } from "@/lib/hooks/use-execution-trajectory";
import { cn } from "@/lib/utils";
import type { EfficiencyScore, TrajectoryStep } from "@/types/trajectory";

export interface TrajectoryVizProps {
  executionId: string;
  anchorStepIndex?: number;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Time unavailable";
  }
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function badgeClasses(score: EfficiencyScore): string {
  if (score === "high") {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700";
  }
  if (score === "medium") {
    return "border-amber-500/30 bg-amber-500/10 text-amber-700";
  }
  if (score === "low") {
    return "border-rose-500/30 bg-rose-500/10 text-rose-700";
  }
  return "border-border/70 bg-muted/60 text-muted-foreground";
}

function badgeLabel(score: EfficiencyScore): string {
  if (score === "high") {
    return "High efficiency";
  }
  if (score === "medium") {
    return "Medium efficiency";
  }
  if (score === "low") {
    return "Low efficiency";
  }
  return "Unscored";
}

function TrajectoryRow({
  step,
  highlighted,
  registerRef,
}: {
  step: TrajectoryStep;
  highlighted: boolean;
  registerRef?: (node: HTMLDivElement | null) => void;
}) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-border/60 bg-background/80 p-4 shadow-sm transition-colors",
        highlighted ? "border-brand-accent/50 bg-brand-accent/5 ring-1 ring-brand-accent/30" : undefined,
      )}
      data-testid={highlighted ? `trajectory-step-highlight-${step.index}` : undefined}
      ref={registerRef}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">Step {step.index}</Badge>
            <Badge className={badgeClasses(step.efficiencyScore)} variant="outline">
              {badgeLabel(step.efficiencyScore)}
            </Badge>
          </div>
          <p className="font-medium text-foreground">{step.toolOrAgentFqn}</p>
        </div>
        <div className="grid min-w-[180px] gap-1 text-right text-sm text-muted-foreground">
          <span>{step.durationMs}ms</span>
          <span>{step.tokenUsage.prompt + step.tokenUsage.completion} tokens</span>
          <span>{formatTimestamp(step.startedAt)}</span>
        </div>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{step.summary}</p>
    </div>
  );
}

export function TrajectoryViz({ executionId, anchorStepIndex }: TrajectoryVizProps) {
  const trajectoryQuery = useExecutionTrajectory(executionId);
  const steps = trajectoryQuery.data ?? [];
  const shouldVirtualize = steps.length > 100;
  const parentRef = useRef<HTMLDivElement | null>(null);
  const anchorRefs = useRef(new Map<number, HTMLDivElement>());

  const rowVirtualizer = useVirtualizer({
    count: steps.length,
    estimateSize: () => 116,
    getScrollElement: () => parentRef.current,
    overscan: 6,
  });

  useEffect(() => {
    if (!anchorStepIndex || steps.length === 0) {
      return;
    }

    const targetIndex = anchorStepIndex - 1;
    if (targetIndex < 0 || targetIndex >= steps.length) {
      return;
    }

    if (shouldVirtualize) {
      window.requestAnimationFrame(() => {
        rowVirtualizer.scrollToIndex(targetIndex, { align: "center" });
      });
      return;
    }

    anchorRefs.current.get(anchorStepIndex)?.scrollIntoView({
      block: "center",
      behavior: "smooth",
    });
  }, [anchorStepIndex, rowVirtualizer, shouldVirtualize, steps.length]);

  const virtualItems = rowVirtualizer.getVirtualItems();
  const showingCount = useMemo(
    () => (shouldVirtualize ? virtualItems.length : steps.length),
    [shouldVirtualize, steps.length, virtualItems.length],
  );

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Trajectory</CardTitle>
        <p className="text-sm text-muted-foreground">
          End-to-end execution timeline with efficiency badges and deep-linkable step anchors.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {trajectoryQuery.isLoading ? (
          Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-28 rounded-2xl" />
          ))
        ) : steps.length === 0 ? (
          <EmptyState
            description="No trajectory steps are available for this execution."
            title="Trajectory unavailable"
          />
        ) : (
          <>
            {shouldVirtualize ? (
              <div className="rounded-2xl border border-border/60 bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
                Showing {showingCount} of {steps.length} steps
              </div>
            ) : null}
            <div className="max-h-[720px] overflow-auto pr-1" ref={parentRef}>
              {shouldVirtualize ? (
                <div
                  className="relative w-full"
                  style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
                >
                  {virtualItems.map((virtualItem) => {
                    const step = steps[virtualItem.index];
                    if (!step) {
                      return null;
                    }

                    return (
                      <div
                        key={virtualItem.key}
                        ref={rowVirtualizer.measureElement}
                        style={{
                          position: "absolute",
                          top: 0,
                          width: "100%",
                          transform: `translateY(${virtualItem.start}px)`,
                        }}
                      >
                        <div className="pb-4">
                          <TrajectoryRow
                            highlighted={anchorStepIndex === step.index}
                            step={step}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="space-y-4">
                  {steps.map((step) => (
                    <TrajectoryRow
                      key={`${step.index}-${step.toolOrAgentFqn}`}
                      highlighted={anchorStepIndex === step.index}
                      registerRef={(node) => {
                        if (node) {
                          anchorRefs.current.set(step.index, node);
                        } else {
                          anchorRefs.current.delete(step.index);
                        }
                      }}
                      step={step}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
