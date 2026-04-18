"use client";

import { AlertCircle, RefreshCw, Scissors, SlidersHorizontal } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatUsd } from "@/lib/analytics";
import type { OptimizationRecommendation } from "@/types/analytics";

export interface RecommendationCardProps {
  recommendation: OptimizationRecommendation;
}

const iconByRecommendationType = {
  model_switch: RefreshCw,
  self_correction_tuning: SlidersHorizontal,
  context_optimization: Scissors,
  underutilization: AlertCircle,
} as const;

const confidenceTone = {
  high: "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  medium: "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300",
  low: "border-border/70 bg-muted/70 text-muted-foreground",
} as const;

export function RecommendationCard({ recommendation }: RecommendationCardProps) {
  const Icon = iconByRecommendationType[recommendation.recommendation_type];

  return (
    <Card className="rounded-[1.5rem] border-border/60">
      <CardHeader className="gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-2xl border border-border/60 bg-muted/60 p-3">
              <Icon className="h-4 w-4 text-brand-accent" />
            </div>
            <div className="space-y-1">
              <CardTitle className="text-base">{recommendation.title}</CardTitle>
              <p className="text-sm text-muted-foreground">
                {recommendation.description}
              </p>
            </div>
          </div>
          <Badge className={confidenceTone[recommendation.confidence]} variant="outline">
            {recommendation.confidence}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-3 text-sm">
        <p className="text-muted-foreground">{recommendation.agent_fqn}</p>
        <p className="font-medium">
          Save ~{formatUsd(recommendation.estimated_savings_usd_per_month)}/mo
        </p>
      </CardContent>
    </Card>
  );
}
