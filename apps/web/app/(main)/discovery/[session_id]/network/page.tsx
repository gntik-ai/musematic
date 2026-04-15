"use client";

import { Network } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { CycleSnapshotSelector } from "@/components/features/discovery/CycleSnapshotSelector";
import { HypothesisNetworkGraph } from "@/components/features/discovery/HypothesisNetworkGraph";
import { useDiscoveryNetwork } from "@/lib/hooks/use-discovery-network";

interface DiscoveryNetworkPageProps {
  params: {
    session_id: string;
  };
}

export default function DiscoveryNetworkPage({ params }: DiscoveryNetworkPageProps) {
  const network = useDiscoveryNetwork(params.session_id);

  if (network.isLoading) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-16 rounded-3xl" />
        <Skeleton className="h-[720px] rounded-[2rem]" />
      </div>
    );
  }

  if (network.isError) {
    return (
      <EmptyState
        description="The discovery network could not be loaded."
        icon={Network}
        title="Discovery unavailable"
      />
    );
  }

  return (
    <div className="space-y-6">
      <header className="overflow-hidden rounded-[2rem] border bg-[linear-gradient(120deg,hsl(var(--foreground))_0%,hsl(var(--foreground)/0.72)_42%,hsl(var(--brand-accent)/0.75)_100%)] p-6 text-background shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <Badge className="mb-3 bg-background/15 text-background hover:bg-background/20">
              {network.landscapeStatus}
            </Badge>
            <h1 className="max-w-3xl text-3xl font-semibold tracking-tight md:text-4xl">
              Scientific discovery network
            </h1>
            <p className="mt-3 max-w-2xl text-sm text-background/78">
              Explore hypotheses by Elo strength, confidence, and semantic proximity.
            </p>
          </div>
          <CycleSnapshotSelector
            snapshots={network.snapshots}
            value={network.selectedSnapshot}
            onChange={network.setSelectedSnapshot}
          />
        </div>
      </header>

      <HypothesisNetworkGraph clusters={network.clusters} hypotheses={network.hypotheses} />
    </div>
  );
}
