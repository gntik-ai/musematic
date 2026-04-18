"use client";

import { Progress } from "@/components/ui/progress";
import { formatUsd } from "@/lib/analytics";
import { cn } from "@/lib/utils";

export interface BudgetUtilizationBarProps {
  workspaceName: string;
  currentSpendUsd: number;
  allocatedBudgetUsd: number | null;
}

function toneForRatio(ratio: number): string {
  if (ratio > 0.9) {
    return "bg-destructive";
  }
  if (ratio >= 0.75) {
    return "bg-[hsl(var(--warning))]";
  }
  return "bg-[hsl(var(--brand-primary))]";
}

export function BudgetUtilizationBar({
  workspaceName,
  currentSpendUsd,
  allocatedBudgetUsd,
}: BudgetUtilizationBarProps) {
  const progress =
    allocatedBudgetUsd && allocatedBudgetUsd > 0
      ? Math.min(100, (currentSpendUsd / allocatedBudgetUsd) * 100)
      : 0;

  return (
    <div className="space-y-3 rounded-[1.25rem] border border-border/60 bg-muted/30 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="font-medium">{workspaceName}</p>
          <p className="text-sm text-muted-foreground">
            {allocatedBudgetUsd === null
              ? "No budget configured"
              : `${formatUsd(currentSpendUsd)} of ${formatUsd(allocatedBudgetUsd)}`}
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm font-medium">{formatUsd(currentSpendUsd)}</p>
          {allocatedBudgetUsd !== null ? (
            <p className="text-xs text-muted-foreground">
              {Math.round(progress)}%
            </p>
          ) : null}
        </div>
      </div>
      <Progress
        indicatorClassName={cn(toneForRatio(progress))}
        value={progress}
      />
    </div>
  );
}
