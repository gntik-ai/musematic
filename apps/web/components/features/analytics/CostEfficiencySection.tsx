"use client";

import type { CSSProperties } from "react";
import { useMemo, useState } from "react";
import { SectionError } from "@/components/features/home/SectionError";
import { CostEfficiencyScatter } from "@/components/features/analytics/CostEfficiencyScatter";
import { CostEfficiencyTable } from "@/components/features/analytics/CostEfficiencyTable";
import { RecommendationCard } from "@/components/features/analytics/RecommendationCard";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Popover, PopoverContent } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useCostIntelligence } from "@/lib/hooks/use-cost-intelligence";
import { useOptimizationRecommendations } from "@/lib/hooks/use-optimization-recommendations";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { formatUsd } from "@/lib/analytics";
import type { AnalyticsFilters, ScatterPoint } from "@/types/analytics";

interface CostEfficiencySectionProps {
  filters: AnalyticsFilters;
}

export function CostEfficiencySection({ filters }: CostEfficiencySectionProps) {
  const isMobile = useMediaQuery("(max-width: 767px)");
  const [selectedAgent, setSelectedAgent] = useState<ScatterPoint | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<{ x: number; y: number } | null>(null);
  const intelligenceQuery = useCostIntelligence(filters);
  const recommendationsQuery = useOptimizationRecommendations(filters.workspaceId);

  const agents = useMemo<ScatterPoint[]>(
    () =>
      (intelligenceQuery.data?.agents ?? []).map((agent) => ({
        agentFqn: agent.agent_fqn,
        modelId: agent.model_id,
        provider: agent.provider,
        costUsd: agent.total_cost_usd,
        qualityScore: agent.avg_quality_score,
        executionCount: agent.execution_count,
        efficiencyRank: agent.efficiency_rank,
        hasQualityData: agent.avg_quality_score !== null,
      })),
    [intelligenceQuery.data?.agents],
  );

  return (
    <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <Card className="rounded-[1.75rem]">
        <CardHeader>
          <CardTitle>Cost efficiency</CardTitle>
          <p className="text-sm text-muted-foreground">
            Map spend against quality to find expensive agents that are not earning
            their keep.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {intelligenceQuery.isPending ? (
            <Skeleton className="h-[400px] rounded-[1.25rem]" />
          ) : intelligenceQuery.isError ? (
            <SectionError
              message="Efficiency analytics could not be loaded."
              title="Cost efficiency unavailable"
            />
          ) : isMobile ? (
            <CostEfficiencyTable agents={agents} />
          ) : (
            <div
              className="relative"
              style={
                {
                  "--analytics-popover-left": `${selectedPosition?.x ?? 24}px`,
                  "--analytics-popover-top": `${selectedPosition?.y ?? 24}px`,
                } as CSSProperties
              }
            >
              <CostEfficiencyScatter
                agents={agents}
                onAgentClick={(agent, position) => {
                  setSelectedAgent(agent);
                  setSelectedPosition(position);
                }}
              />
              <Popover
                open={Boolean(selectedAgent)}
                onOpenChange={(open) => {
                  if (!open) {
                    setSelectedAgent(null);
                    setSelectedPosition(null);
                  }
                }}
              >
                <PopoverContent className="[left:var(--analytics-popover-left)] [top:var(--analytics-popover-top)] w-[22rem] rounded-[1.25rem] border border-border/60 bg-background/95 p-4 text-sm shadow-xl">
                  {selectedAgent ? (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-semibold">{selectedAgent.agentFqn}</p>
                          <p className="text-muted-foreground">
                            {selectedAgent.modelId} · {selectedAgent.provider}
                          </p>
                        </div>
                        <button
                          className="text-muted-foreground transition hover:text-foreground"
                          onClick={() => {
                            setSelectedAgent(null);
                            setSelectedPosition(null);
                          }}
                          type="button"
                        >
                          Close
                        </button>
                      </div>
                      <dl className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <dt className="text-muted-foreground">Cost</dt>
                          <dd className="font-medium">{formatUsd(selectedAgent.costUsd)}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Quality score</dt>
                          <dd className="font-medium">
                            {selectedAgent.qualityScore === null
                              ? "No quality data"
                              : selectedAgent.qualityScore.toFixed(2)}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Execution count</dt>
                          <dd className="font-medium">{selectedAgent.executionCount}</dd>
                        </div>
                        <div>
                          <dt className="text-muted-foreground">Efficiency rank</dt>
                          <dd className="font-medium">#{selectedAgent.efficiencyRank}</dd>
                        </div>
                      </dl>
                    </div>
                  ) : null}
                </PopoverContent>
              </Popover>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-[1.75rem]">
        <CardHeader>
          <CardTitle>Optimization recommendations</CardTitle>
          <p className="text-sm text-muted-foreground">
            AI-suggested levers to reduce cost without bluntly sacrificing quality.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {recommendationsQuery.isPending ? (
            <>
              <Skeleton className="h-28 rounded-[1.25rem]" />
              <Skeleton className="h-28 rounded-[1.25rem]" />
            </>
          ) : recommendationsQuery.isError ? (
            <SectionError
              message="Recommendations could not be loaded."
              title="Recommendations unavailable"
            />
          ) : recommendationsQuery.data?.recommendations.length ? (
            recommendationsQuery.data.recommendations.map((recommendation) => (
              <RecommendationCard
                key={`${recommendation.agent_fqn}-${recommendation.recommendation_type}`}
                recommendation={recommendation}
              />
            ))
          ) : (
            <EmptyState
              description="Recommendations will appear after more usage data is available."
              title="No recommendations yet"
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
