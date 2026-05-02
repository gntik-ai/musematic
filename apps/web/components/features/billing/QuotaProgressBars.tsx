"use client";

import { Progress } from "@/components/ui/progress";
import type { BillingPlanCaps, BillingUsage } from "@/lib/hooks/use-workspace-billing";

interface QuotaProgressBarsProps {
  caps: BillingPlanCaps;
  usage: BillingUsage;
}

function percent(current: number, limit: number): number {
  if (limit <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((current / limit) * 100));
}

function tone(value: number): string {
  if (value >= 100) {
    return "text-destructive";
  }
  if (value >= 80) {
    return "text-amber-600";
  }
  return "text-muted-foreground";
}

export function QuotaProgressBars({ caps, usage }: QuotaProgressBarsProps) {
  const items = [
    ["Executions today", usage.executions_today, caps.executions_per_day],
    ["Executions period", usage.executions_this_period, caps.executions_per_month],
    ["Minutes today", Number(usage.minutes_today), caps.minutes_per_day],
    ["Minutes period", Number(usage.minutes_this_period), caps.minutes_per_month],
  ] as const;

  return (
    <div className="space-y-4">
      {items.map(([label, current, limit]) => {
        const value = percent(current, limit);
        return (
          <div key={label} className="space-y-2">
            <div className="flex items-center justify-between gap-4 text-sm">
              <span className="font-medium">{label}</span>
              <span className={tone(value)}>{limit === 0 ? "Unlimited" : `${current} / ${limit}`}</span>
            </div>
            <Progress value={limit === 0 ? 0 : value} />
          </div>
        );
      })}
    </div>
  );
}
