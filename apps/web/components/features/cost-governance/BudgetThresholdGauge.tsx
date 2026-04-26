"use client";

import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface BudgetThresholdGaugeProps {
  currentSpendCents: number;
  budgetCents: number;
  thresholds: number[];
}

export function budgetThresholdTone(percent: number): "ok" | "warn" | "danger" {
  if (percent >= 100) {
    return "danger";
  }
  if (percent >= 80) {
    return "warn";
  }
  return "ok";
}

export function BudgetThresholdGauge({
  budgetCents,
  currentSpendCents,
  thresholds,
}: BudgetThresholdGaugeProps) {
  const percent = budgetCents > 0 ? Math.min((currentSpendCents / budgetCents) * 100, 140) : 0;
  const tone = budgetThresholdTone(percent);

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-2xl font-semibold">${(currentSpendCents / 100).toFixed(2)}</span>
        <span className="text-sm text-muted-foreground">${(budgetCents / 100).toFixed(2)}</span>
      </div>
      <div className="relative pb-5">
        <Progress
          className={cn(
            "h-3",
            tone === "warn" && "[&>div]:bg-amber-500",
            tone === "danger" && "[&>div]:bg-destructive",
          )}
          value={Math.min(percent, 100)}
        />
        {thresholds.map((threshold) => (
          <span
            key={threshold}
            className="absolute top-4 h-2 border-l border-muted-foreground text-[10px] text-muted-foreground"
            style={{ left: `${Math.min(threshold, 100)}%` }}
          >
            <span className="ml-1">{threshold}%</span>
          </span>
        ))}
      </div>
      <div
        className={cn(
          "text-sm font-medium",
          tone === "ok" && "text-emerald-600",
          tone === "warn" && "text-amber-600",
          tone === "danger" && "text-destructive",
        )}
      >
        {percent.toFixed(1)}%
      </div>
    </div>
  );
}
