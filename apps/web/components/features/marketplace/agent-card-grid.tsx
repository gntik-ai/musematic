"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, SearchX } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentCard } from "@/components/features/marketplace/agent-card";
import { useComparisonStore } from "@/lib/stores/use-comparison-store";
import { buildAgentHref, type AgentCard as MarketplaceAgentCard } from "@/lib/types/marketplace";

export interface AgentCardGridProps {
  agents: MarketplaceAgentCard[];
  isLoading: boolean;
  isError: boolean;
  hasNextPage: boolean;
  onLoadMore: () => void;
  isFetchingNextPage: boolean;
  emptyState?: React.ReactNode;
}

export function AgentCardGrid({
  agents,
  isLoading,
  isError,
  hasNextPage,
  onLoadMore,
  isFetchingNextPage,
  emptyState,
}: AgentCardGridProps) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const selectedFqns = useComparisonStore((state) => state.selectedFqns);
  const toggle = useComparisonStore((state) => state.toggle);

  useEffect(() => {
    if (!hasNextPage || !sentinelRef.current) {
      return undefined;
    }

    const observer = new window.IntersectionObserver((entries) => {
      const [entry] = entries;
      if (entry?.isIntersecting) {
        onLoadMore();
      }
    });

    observer.observe(sentinelRef.current);

    return () => {
      observer.disconnect();
    };
  }, [hasNextPage, onLoadMore]);

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => (
          <div
            key={index}
            className="space-y-4 rounded-3xl border border-border/60 bg-card/70 p-6"
          >
            <div className="flex gap-2">
              <Skeleton className="h-6 w-24 rounded-full" />
              <Skeleton className="h-6 w-20 rounded-full" />
            </div>
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-24 w-full rounded-2xl" />
            <div className="flex justify-between gap-3">
              <Skeleton className="h-9 w-28 rounded-xl" />
              <Skeleton className="h-9 w-24 rounded-xl" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <EmptyState
        description="The marketplace could not load right now. Try refreshing the page."
        icon={AlertTriangle}
        title="Unable to load agents"
      />
    );
  }

  if (agents.length === 0) {
    return (
      <>
        {emptyState ?? (
          <EmptyState
            description="Broaden the search or remove some filters to discover more agents."
            icon={SearchX}
            title="No agents match your search"
          />
        )}
      </>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            href={buildAgentHref(agent.namespace, agent.localName)}
            isSelected={selectedFqns.includes(agent.fqn)}
            onToggleCompare={toggle}
          />
        ))}
      </div>

      {hasNextPage ? <div ref={sentinelRef} className="h-1" /> : null}

      {isFetchingNextPage ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }, (_, index) => (
            <Skeleton key={index} className="h-[240px] rounded-3xl" />
          ))}
        </div>
      ) : null}
    </div>
  );
}
