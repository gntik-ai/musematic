"use client";

import { MetricCard } from "@/components/shared/MetricCard";
import type { EvaluationRunResponse } from "@/types/evaluation";

export interface AggregateMetricsProps {
  run: Pick<
    EvaluationRunResponse,
    "total_cases" | "passed_cases" | "failed_cases" | "aggregate_score"
  >;
}

export function AggregateMetrics({ run }: AggregateMetricsProps) {
  const averageScore =
    typeof run.aggregate_score === "number"
      ? `${Math.round(run.aggregate_score * 100)}%`
      : "—";

  return (
    <div
      className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"
      role="status"
    >
      <MetricCard title="Total Cases" value={run.total_cases} />
      <MetricCard title="Passed" trend="up" value={run.passed_cases} />
      <MetricCard title="Failed" trend="down" value={run.failed_cases} />
      <MetricCard title="Average Score" value={averageScore} />
    </div>
  );
}
