"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import {
  getRecommendationLabel,
  buildAgentHref,
  type RecommendationCarousel as RecommendationCarouselData,
} from "@/lib/types/marketplace";
import { AgentCard } from "@/components/features/marketplace/agent-card";
import { useComparisonStore } from "@/lib/stores/use-comparison-store";

export interface RecommendationCarouselProps {
  data: RecommendationCarouselData;
  isLoading: boolean;
}

export function RecommendationCarousel({
  data,
  isLoading,
}: RecommendationCarouselProps) {
  const selectedFqns = useComparisonStore((state) => state.selectedFqns);
  const toggle = useComparisonStore((state) => state.toggle);

  if (isLoading || data.agents.length < 3) {
    return null;
  }

  return (
    <section
      aria-label="Recommended agents"
      className="space-y-4 rounded-3xl border border-border/60 bg-card/70 p-5 shadow-sm"
      role="region"
    >
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-brand-accent">
          Discovery
        </p>
        <h2 className="mt-2 text-2xl font-semibold">
          {getRecommendationLabel(data.reason)}
        </h2>
      </div>
      <ScrollArea className="w-full">
        <div className="flex gap-4 pb-2">
          {data.agents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              compact
              href={buildAgentHref(agent.namespace, agent.localName)}
              isSelected={selectedFqns.includes(agent.fqn)}
              onToggleCompare={toggle}
            />
          ))}
        </div>
      </ScrollArea>
    </section>
  );
}
