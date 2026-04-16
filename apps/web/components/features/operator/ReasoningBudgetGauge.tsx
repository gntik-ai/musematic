"use client";

import { AlertTriangle } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { ScoreGauge } from "@/components/shared/ScoreGauge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ReasoningBudgetUtilization } from "@/lib/types/operator-dashboard";

export interface ReasoningBudgetGaugeProps {
  utilization: ReasoningBudgetUtilization | undefined;
  isLoading: boolean;
  error?: boolean;
}

export function ReasoningBudgetGauge({
  utilization,
  isLoading,
  error = false,
}: ReasoningBudgetGaugeProps) {
  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Reasoning budget</CardTitle>
        <p className="text-sm text-muted-foreground">
          Aggregate token capacity pressure across active executions.
        </p>
      </CardHeader>
      <CardContent className="flex min-h-[280px] flex-col items-center justify-center gap-4">
        {isLoading ? (
          <Skeleton className="h-48 w-48 rounded-full" />
        ) : error || !utilization ? (
          <EmptyState
            description="Budget data unavailable"
            title="Reasoning budget unavailable"
          />
        ) : (
          <>
            <ScoreGauge
              label="Utilization"
              score={Math.round(utilization.utilizationPct)}
              size={160}
              thresholds={{ warning: 70, good: 90 }}
              tone="lower-is-better"
              valueLabel={`${Math.round(utilization.utilizationPct)}%`}
            />
            <p className="text-sm text-muted-foreground">
              {utilization.activeExecutionCount} active executions
            </p>
            {utilization.criticalPressure ? (
              <p className="flex items-center gap-2 font-semibold text-destructive">
                <AlertTriangle className="h-4 w-4" />
                Capacity pressure
              </p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
