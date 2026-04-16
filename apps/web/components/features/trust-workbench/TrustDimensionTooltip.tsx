"use client";

import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TRUST_DIMENSION_LABELS, type TrustDimensionScore } from "@/lib/types/trust-workbench";

export interface TrustDimensionTooltipProps {
  active?: boolean | undefined;
  payload?: Array<{
    name?: string;
    value?: number;
    payload?: {
      dimension?: keyof typeof TRUST_DIMENSION_LABELS;
    };
  }> | undefined;
  dimensionScores: TrustDimensionScore[];
}

function TrendIcon({
  trend,
}: {
  trend: "up" | "down" | "stable" | undefined;
}) {
  if (trend === "up") {
    return <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />;
  }
  if (trend === "down") {
    return <TrendingDown className="h-3.5 w-3.5 text-destructive" />;
  }

  return <Minus className="h-3.5 w-3.5 text-muted-foreground" />;
}

export function TrustDimensionTooltip({
  active,
  payload,
  dimensionScores,
}: TrustDimensionTooltipProps) {
  const dimensionId = payload?.[0]?.payload?.dimension;
  const score = payload?.[0]?.value ?? 0;
  const dimension = dimensionScores.find((item) => item.dimension === dimensionId);

  if (!active || !dimensionId || !dimension) {
    return null;
  }

  return (
    <Card className="w-72 border-border/70 bg-background/95 shadow-lg">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {TRUST_DIMENSION_LABELS[dimensionId]}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">{score} / 100</p>
        <div className="space-y-2">
          {dimension.components.map((component) => (
            <div
              key={`${dimension.dimension}-${component.name}`}
              className="flex items-center justify-between gap-3 rounded-xl border border-border/60 bg-card/70 px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2">
                <TrendIcon trend={component.trend} />
                <span>{component.name}</span>
              </div>
              <div className="text-right">
                <div className="font-medium">{component.score}</div>
                {dimension.dimension === "behavioral_compliance" &&
                typeof component.anomalyCount === "number" ? (
                  <div className="text-xs text-muted-foreground">
                    {component.anomalyCount} anomalies
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
