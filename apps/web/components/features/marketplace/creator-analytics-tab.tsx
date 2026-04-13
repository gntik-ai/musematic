"use client";

import { AlertTriangle, BarChart3 } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreatorAnalytics } from "@/lib/hooks/use-creator-analytics";
import { UsageChart } from "@/components/features/marketplace/usage-chart";
import { SatisfactionTrendChart } from "@/components/features/marketplace/satisfaction-trend-chart";

export interface CreatorAnalyticsTabProps {
  agentFqn: string;
}

export function CreatorAnalyticsTab({
  agentFqn,
}: CreatorAnalyticsTabProps) {
  const analyticsQuery = useCreatorAnalytics(agentFqn);

  if (analyticsQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-64 rounded-3xl" />
        <Skeleton className="h-64 rounded-3xl" />
      </div>
    );
  }

  if (analyticsQuery.isError || !analyticsQuery.data) {
    return (
      <EmptyState
        description="Creator analytics could not be loaded for this agent."
        icon={AlertTriangle}
        title="Analytics unavailable"
      />
    );
  }

  const { commonFailures, periodDays, satisfactionTrend, usageChart } =
    analyticsQuery.data;

  if (
    usageChart.length === 0 &&
    satisfactionTrend.length === 0 &&
    commonFailures.length === 0
  ) {
    return (
      <EmptyState
        description="Usage and rating signals will appear here once the agent is invoked."
        icon={BarChart3}
        title="No usage data yet"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-2">
        <UsageChart data={usageChart} periodDays={periodDays} />
        <SatisfactionTrendChart data={satisfactionTrend} />
      </div>
      <div className="rounded-3xl border border-border/60 bg-card/70 p-5">
        <div className="mb-4">
          <p className="text-sm font-semibold">Common failures</p>
          <p className="text-sm text-muted-foreground">
            Categories most frequently associated with unsuccessful invocations.
          </p>
        </div>
        <div className="space-y-3">
          {commonFailures.map((failure) => (
            <div
              key={failure.category}
              className="flex items-center justify-between gap-3 rounded-2xl border border-border/60 bg-background/60 px-4 py-3"
            >
              <div>
                <p className="font-medium">{failure.category}</p>
                <p className="text-sm text-muted-foreground">
                  {failure.count} occurrences
                </p>
              </div>
              <div className="text-right">
                <p className="font-semibold">{failure.percentage.toFixed(0)}%</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
