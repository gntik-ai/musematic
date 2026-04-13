"use client";

import { format } from "date-fns";
import { Card, CardContent } from "@/components/ui/card";
import type { QualityMetrics as MarketplaceQualityMetrics } from "@/lib/types/marketplace";

export interface QualityMetricsProps {
  metrics: MarketplaceQualityMetrics;
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function QualityMetrics({ metrics }: QualityMetricsProps) {
  const items = [
    {
      label: "Evaluation score",
      value: formatPercent(metrics.evaluationScore),
    },
    {
      label: "Robustness score",
      value: formatPercent(metrics.robustnessScore),
    },
    {
      label: "Pass rate",
      value: formatPercent(metrics.passRate),
    },
    {
      label: "Last evaluated",
      value: metrics.lastEvaluatedAt
        ? format(new Date(metrics.lastEvaluatedAt), "MMM d, yyyy")
        : "—",
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Card key={item.label}>
          <CardContent className="space-y-2 p-5">
            <p className="text-sm text-muted-foreground">{item.label}</p>
            <p className="text-2xl font-semibold">{item.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
