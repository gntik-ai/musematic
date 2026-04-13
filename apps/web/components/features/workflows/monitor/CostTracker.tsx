"use client";

import { useEffect, useMemo, useState } from "react";
import { Coins, ReceiptText } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useCostTracker } from "@/lib/hooks/use-cost-tracker";
import { cn } from "@/lib/utils";

function formatUsd(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(value);
}

export function CostTracker({
  executionId,
}: {
  executionId: string;
}) {
  const {
    breakdownQuery,
    costBreakdown,
    expandedBreakdown,
    totalCostUsd,
    totalTokens,
  } =
    useCostTracker(executionId);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (expanded) {
      void expandedBreakdown();
    }
  }, [expanded, expandedBreakdown]);

  const stepBreakdown = useMemo(
    () =>
      costBreakdown.length > 0
        ? costBreakdown
        : breakdownQuery.data?.stepBreakdown ?? [],
    [breakdownQuery.data?.stepBreakdown, costBreakdown],
  );
  const highestCostStepId = useMemo(
    () => stepBreakdown[0]?.stepId ?? null,
    [stepBreakdown],
  );

  if (totalTokens === 0) {
    return (
      <EmptyState
        description="Cost data will appear as soon as token usage is recorded for this execution."
        icon={Coins}
        title="No cost data yet"
      />
    );
  }

  return (
    <div className="rounded-3xl border border-border/70 bg-background/95 p-4 shadow-xl">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <Badge className="gap-2" variant="outline">
            <ReceiptText className="h-4 w-4" />
            {totalTokens.toLocaleString()} tokens
          </Badge>
          <Badge className="gap-2" variant="outline">
            <Coins className="h-4 w-4" />
            {formatUsd(totalCostUsd)}
          </Badge>
        </div>

        <Collapsible
          open={expanded}
          onOpenChange={setExpanded}
        >
          <CollapsibleTrigger className="rounded-md border border-border bg-background px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground">
            {expanded ? "Hide breakdown" : "Expand breakdown"}
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-4 space-y-3">
              {breakdownQuery.isFetching ? (
                <p className="text-sm text-muted-foreground">
                  Loading cost breakdown...
                </p>
              ) : stepBreakdown.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No per-step breakdown is available yet for this execution.
                </p>
              ) : (
                stepBreakdown.map((step) => (
                  <div
                    className={cn(
                      "rounded-2xl border border-border/60 bg-card/80 p-3",
                      step.stepId === highestCostStepId &&
                        "bg-yellow-50 dark:bg-yellow-950",
                    )}
                    key={step.stepId}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-medium text-foreground">{step.stepName}</p>
                        <p className="text-sm text-muted-foreground">
                          {step.totalTokens.toLocaleString()} tokens
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-medium text-foreground">
                          {formatUsd(step.costUsd)}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {step.percentageOfTotal.toFixed(1)}% of total
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 h-2 rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-brand-primary"
                        style={{ width: `${Math.min(step.percentageOfTotal, 100)}%` }}
                      />
                    </div>
                  </div>
                ))
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>
    </div>
  );
}
