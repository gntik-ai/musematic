"use client";

import Link from "next/link";
import { Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueries } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { createApiClient } from "@/lib/api";
import { ComparisonView } from "@/components/features/marketplace/comparison-view";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { marketplaceQueryKeys } from "@/lib/hooks/use-marketplace-search";
import { useComparisonStore } from "@/lib/stores/use-comparison-store";
import {
  decodeComparisonHandle,
  encodeComparisonHandle,
  type AgentDetail,
} from "@/lib/types/marketplace";

const marketplaceApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function MarketplaceComparePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const removeFromComparison = useComparisonStore((state) => state.remove);

  const comparisonHandles = useMemo(() => {
    const raw = searchParams.get("agents");
    if (!raw) {
      return [];
    }

    return raw
      .split(",")
      .map((token) => decodeComparisonHandle(token))
      .slice(0, 4);
  }, [searchParams]);

  const backQuery = searchParams.get("back");
  const backHref = backQuery ? `/marketplace?${backQuery}` : "/marketplace";

  const queries = useQueries({
    queries: comparisonHandles.map(({ namespace, localName }) => ({
      queryKey: marketplaceQueryKeys.agent(namespace, localName),
      queryFn: () =>
        marketplaceApi.get<AgentDetail>(
          `/api/v1/marketplace/agents/${encodeURIComponent(namespace)}/${encodeURIComponent(localName)}`,
        ),
      staleTime: 30_000,
    })),
  });

  const isLoading = queries.some((query) => query.isLoading);
  const isError = queries.some((query) => query.isError);
  const agents = queries
    .map((query) => query.data)
    .filter((agent): agent is AgentDetail => Boolean(agent));

  const updateAgents = (nextAgents: string[]) => {
    const nextParams = new URLSearchParams();
    if (nextAgents.length > 0) {
      nextParams.set("agents", nextAgents.join(","));
    }
    if (backQuery) {
      nextParams.set("back", backQuery);
    }
    const nextQuery = nextParams.toString();
    router.push(nextQuery ? `/marketplace/compare?${nextQuery}` : "/marketplace");
  };

  if (isLoading) {
    return <Skeleton className="h-[420px] rounded-3xl" />;
  }

  if (isError) {
    return (
      <EmptyState
        description="One or more agent details could not be loaded for comparison."
        icon={AlertTriangle}
        title="Comparison unavailable"
      />
    );
  }

  if (agents.length < 2) {
    return (
      <EmptyState
        description="Select at least two agents from the marketplace to compare them side by side."
        icon={AlertTriangle}
        title="Not enough agents selected"
      />
    );
  }

  return (
    <section className="space-y-4">
      <Link
        className="inline-flex text-sm font-medium text-brand-primary transition hover:text-brand-primary/80"
        href={backHref}
      >
        Back to Marketplace
      </Link>
      <div>
        <h1 className="text-3xl font-semibold">Compare agents</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Review capabilities, trust, quality, and cost before choosing an agent for your workflow.
        </p>
      </div>
      <ComparisonView
        agents={agents}
        onRemove={(fqn) => {
          removeFromComparison(fqn);
          updateAgents(
            comparisonHandles
              .map(({ namespace, localName }) =>
                encodeComparisonHandle(`${namespace}:${localName}`),
              )
              .filter((value) => value !== encodeComparisonHandle(fqn)),
          );
        }}
      />
    </section>
  );
}

export default function MarketplaceComparePage() {
  return (
    <Suspense fallback={<Skeleton className="h-[420px] rounded-3xl" />}>
      <MarketplaceComparePageContent />
    </Suspense>
  );
}
