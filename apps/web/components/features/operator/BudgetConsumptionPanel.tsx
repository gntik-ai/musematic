"use client";

import { AlertTriangle } from "lucide-react";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import type { BudgetStatus } from "@/lib/types/operator-dashboard";

export interface BudgetConsumptionPanelProps {
  budget: BudgetStatus | undefined;
  isLoading: boolean;
}

function indicatorClassName(utilizationPct: number): string {
  if (utilizationPct >= 90) {
    return "bg-red-500";
  }
  if (utilizationPct >= 70) {
    return "bg-yellow-500";
  }

  return "bg-blue-500";
}

export function BudgetConsumptionPanel({
  budget,
  isLoading,
}: BudgetConsumptionPanelProps) {
  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Budget consumption</CardTitle>
        <p className="text-sm text-muted-foreground">
          Runtime resource usage against execution limits.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="space-y-2">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-3 w-full rounded-full" />
            </div>
          ))
        ) : budget ? (
          <>
            {!budget.isActive ? (
              <Alert>
                <AlertTitle>Execution completed — final values</AlertTitle>
                <AlertDescription>
                  These budget values reflect the final execution snapshot.
                </AlertDescription>
              </Alert>
            ) : null}

            {budget.dimensions.map((dimension) => (
              <div key={dimension.dimension} className="space-y-2">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{dimension.label}</span>
                    {dimension.nearLimit ? (
                      <AlertTriangle className="h-4 w-4 text-yellow-500" />
                    ) : null}
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {dimension.used} / {dimension.limit} {dimension.unit}
                  </span>
                </div>
                <Progress
                  indicatorClassName={indicatorClassName(dimension.utilizationPct)}
                  value={dimension.utilizationPct}
                />
              </div>
            ))}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
