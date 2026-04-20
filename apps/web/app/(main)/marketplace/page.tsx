"use client";

import { Suspense, useMemo } from "react";
import { ChevronsUpDown, Sparkles } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AgentCardGrid } from "@/components/features/marketplace/agent-card-grid";
import {
  AgentCardFqn,
  toAgentCardIdentity,
} from "@/components/features/marketplace/agent-card-fqn";
import { ComparisonFloatingBar } from "@/components/features/marketplace/comparison-floating-bar";
import { FilterSidebar } from "@/components/features/marketplace/filter-sidebar";
import { MarketplaceSearchFqn } from "@/components/features/marketplace/marketplace-search-fqn";
import { RecommendationCarousel } from "@/components/features/marketplace/recommendation-carousel";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Select } from "@/components/ui/select";
import { useMarketplaceFilterMetadata, useMarketplaceSearch } from "@/lib/hooks/use-marketplace-search";
import { useRecommendations } from "@/lib/hooks/use-recommendations";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { parseMarketplaceSearchParams, serializeMarketplaceSearchParams } from "@/lib/schemas/marketplace";
import { useComparisonStore } from "@/lib/stores/use-comparison-store";
import {
  DEFAULT_MARKETPLACE_SEARCH_PARAMS,
  SORT_OPTIONS,
  buildAgentHref,
  encodeComparisonHandle,
  getActiveMarketplaceFilterCount,
  humanizeMarketplaceValue,
} from "@/lib/types/marketplace";

function isLegacyAgent(fqn: string): boolean {
  return !fqn.includes(":");
}

function MarketplacePageContent() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const isMobile = useMediaQuery("(max-width: 640px)");
  const selectedFqns = useComparisonStore((state) => state.selectedFqns);
  const clearComparison = useComparisonStore((state) => state.clear);
  const toggleComparison = useComparisonStore((state) => state.toggle);

  const filters = useMemo(
    () => parseMarketplaceSearchParams(searchParams),
    [searchParams],
  );
  const activeFilterCount = getActiveMarketplaceFilterCount(filters);
  const searchQuery = useMarketplaceSearch(filters);
  const filterMetadataQuery = useMarketplaceFilterMetadata();
  const recommendationsQuery = useRecommendations();

  const agents = useMemo(
    () => searchQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [searchQuery.data],
  );

  const groupedAgents = useMemo(() => {
    const query = filters.q.trim().toLowerCase();
    if (!query) {
      return {
        primary: agents,
        legacy: [] as typeof agents,
      };
    }

    const legacy = agents.filter((agent) => isLegacyAgent(agent.fqn));
    const primary = agents.filter((agent) => {
      if (isLegacyAgent(agent.fqn)) {
        return false;
      }
      return agent.fqn.toLowerCase().startsWith(query);
    });

    return { primary, legacy };
  }, [agents, filters.q]);

  const updateSearchParams = (updated: Partial<typeof filters>) => {
    const nextQuery = serializeMarketplaceSearchParams({
      ...DEFAULT_MARKETPLACE_SEARCH_PARAMS,
      ...filters,
      ...updated,
      page: 1,
    }).toString();

    router.push(nextQuery ? `${pathname}?${nextQuery}` : pathname);
  };

  const visibleCount = groupedAgents.primary.length + groupedAgents.legacy.length;

  return (
    <section className="space-y-6">
      <div className="rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
              <Sparkles className="h-4 w-4" />
              Marketplace
            </div>
            <div>
              <h1 className="text-3xl font-semibold">Discover production-ready agents</h1>
              <p className="mt-2 max-w-3xl text-muted-foreground">
                Browse certified agents, compare trust posture, inspect reviews, and start a conversation from the marketplace.
              </p>
            </div>
          </div>
          <div className="min-w-[220px]">
            <label className="mb-2 block text-sm font-medium" htmlFor="marketplace-sort">
              Sort by
            </label>
            <Select
              id="marketplace-sort"
              value={filters.sortBy}
              onChange={(event) =>
                updateSearchParams({
                  sortBy: event.target.value as typeof filters.sortBy,
                })
              }
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {humanizeMarketplaceValue(option)}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </div>

      <RecommendationCarousel
        data={
          recommendationsQuery.data ?? {
            agents: [],
            reason: "personalized",
            totalAvailable: 0,
          }
        }
        isLoading={recommendationsQuery.isLoading}
      />

      <MarketplaceSearchFqn
        initialQuery={filters.q}
        isLoading={searchQuery.isFetching && !searchQuery.isFetchingNextPage}
        onQueryChange={() => undefined}
      />

      <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <FilterSidebar
          activeFilterCount={activeFilterCount}
          filterMetadata={
            filterMetadataQuery.data ?? {
              capabilities: [],
              tags: [],
            }
          }
          filters={filters}
          isMobile={isMobile}
          onChange={updateSearchParams}
        />
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              {filters.q ? visibleCount : searchQuery.data?.pages[0]?.total ?? agents.length} agents found
            </p>
          </div>
          <AgentCardGrid
            agents={groupedAgents.primary}
            hasNextPage={searchQuery.hasNextPage ?? false}
            isError={searchQuery.isError}
            isFetchingNextPage={searchQuery.isFetchingNextPage}
            isLoading={searchQuery.isLoading}
            onLoadMore={() => {
              if (searchQuery.hasNextPage && !searchQuery.isFetchingNextPage) {
                void searchQuery.fetchNextPage();
              }
            }}
          />

          {filters.q.trim() && groupedAgents.legacy.length > 0 ? (
            <Collapsible defaultOpen={false}>
              <div className="rounded-3xl border border-border/60 bg-card/70 p-4">
                <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 text-left text-sm font-medium">
                  <span>Legacy (uncategorized)</span>
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    {groupedAgents.legacy.length}
                    <ChevronsUpDown className="h-4 w-4" />
                  </span>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {groupedAgents.legacy.map((agent) => {
                      const isSelected = selectedFqns.includes(agent.fqn);
                      const compareDisabled = !isSelected && selectedFqns.length >= 4;

                      return (
                        <AgentCardFqn
                          key={agent.id}
                          agent={toAgentCardIdentity(agent)}
                          compareDisabled={compareDisabled}
                          href={buildAgentHref(agent.namespace, agent.localName)}
                          isSelected={isSelected}
                          onAddToCompare={() => toggleComparison(agent.fqn)}
                        />
                      );
                    })}
                  </div>
                </CollapsibleContent>
              </div>
            </Collapsible>
          ) : null}
        </div>
      </div>

      <ComparisonFloatingBar
        selectedFqns={selectedFqns}
        onClear={clearComparison}
        onCompare={() => {
          const nextParams = new URLSearchParams();
          nextParams.set(
            "agents",
            selectedFqns.map((fqn) => encodeComparisonHandle(fqn)).join(","),
          );
          if (searchParams.toString()) {
            nextParams.set("back", searchParams.toString());
          }
          router.push(`/marketplace/compare?${nextParams.toString()}`);
        }}
      />
    </section>
  );
}

export default function MarketplacePage() {
  return (
    <Suspense fallback={<section className="space-y-6" />}>
      <MarketplacePageContent />
    </Suspense>
  );
}
