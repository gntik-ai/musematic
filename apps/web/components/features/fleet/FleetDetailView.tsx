"use client";

import { useEffect, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FleetControlsPanel } from "@/components/features/fleet/FleetControlsPanel";
import { FleetHealthGauge } from "@/components/features/fleet/FleetHealthGauge";
import { FleetMemberDetailPanel } from "@/components/features/fleet/FleetMemberDetailPanel";
import { FleetMemberPanel } from "@/components/features/fleet/FleetMemberPanel";
import { FleetObserverPanel } from "@/components/features/fleet/FleetObserverPanel";
import { FleetPerformanceCharts } from "@/components/features/fleet/FleetPerformanceCharts";
import { FleetStatusBadge } from "@/components/features/fleet/FleetStatusBadge";
import { FleetTopologyBadge } from "@/components/features/fleet/FleetTopologyBadge";
import { FleetTopologyGraph } from "@/components/features/fleet/FleetTopologyGraph";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useFleet } from "@/lib/hooks/use-fleets";
import { isFleetDetailTab, type FleetDetailTab } from "@/lib/types/fleet";
import { ApiError } from "@/types/api";

interface FleetDetailViewProps {
  fleetId: string;
}

const tabDefinitions: { id: FleetDetailTab; label: string }[] = [
  { id: "topology", label: "Topology" },
  { id: "members", label: "Members" },
  { id: "performance", label: "Performance" },
  { id: "controls", label: "Controls" },
  { id: "observers", label: "Observers" },
];

export function FleetDetailView({ fleetId }: FleetDetailViewProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const fleetQuery = useFleet(fleetId);
  const activeTab = isFleetDetailTab(searchParams.get("tab"))
    ? (searchParams.get("tab") as FleetDetailTab)
    : "topology";
  const selectedNodeId = searchParams.get("member");

  useEffect(() => {
    if (fleetQuery.error instanceof ApiError && fleetQuery.error.status === 404) {
      router.replace("/fleet");
    }
  }, [fleetQuery.error, router]);

  const fleet = fleetQuery.data;

  const updateTab = (tab: FleetDetailTab) => {
    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set("tab", tab);
    router.replace(`${pathname}?${nextParams.toString()}`);
  };

  const updateSelectedMember = (memberId: string | null) => {
    const nextParams = new URLSearchParams(searchParams.toString());
    if (memberId) {
      nextParams.set("member", memberId);
    } else {
      nextParams.delete("member");
    }
    router.replace(`${pathname}?${nextParams.toString()}`);
  };

  const statusLine = useMemo(
    () =>
      fleet
        ? `${fleet.member_count} members · quorum ${fleet.quorum_min} · updated ${new Date(
            fleet.updated_at,
          ).toLocaleString()}`
        : null,
    [fleet],
  );

  if (fleetQuery.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 rounded-[2rem]" />
        <Skeleton className="h-14 rounded-2xl" />
        <Skeleton className="h-[720px] rounded-[2rem]" />
      </div>
    );
  }

  if (fleetQuery.isError || !fleet) {
    return (
      <EmptyState
        description="The fleet detail view could not be loaded."
        title="Fleet unavailable"
      />
    );
  }

  return (
    <div className="space-y-6">
      <header className="overflow-hidden rounded-[2rem] border bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.18),transparent_24%),linear-gradient(140deg,hsl(var(--card))_0%,hsl(var(--muted)/0.52)_100%)] p-6 shadow-sm">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <FleetStatusBadge status={fleet.status} />
              <FleetTopologyBadge topology={fleet.topology_type} />
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
                {fleet.name}
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">{statusLine}</p>
            </div>
          </div>
          <div className="rounded-[1.75rem] border border-border/60 bg-background/75 p-4 shadow-sm">
            <FleetHealthGauge fleetId={fleetId} size="sm" />
          </div>
        </div>
      </header>

      <Tabs>
        <TabsList className="flex w-full flex-wrap gap-2 rounded-[1.5rem] bg-muted/60 p-2">
          {tabDefinitions.map((tab) => (
            <TabsTrigger
              key={tab.id}
              aria-pressed={activeTab === tab.id}
              className={activeTab === tab.id ? "bg-background shadow-sm" : undefined}
              onClick={() => updateTab(tab.id)}
            >
              {tab.label}
            </TabsTrigger>
          ))}
        </TabsList>

        {activeTab === "topology" ? (
          <TabsContent>
            <FleetTopologyGraph fleetId={fleetId} onNodeSelect={updateSelectedMember} />
            {selectedNodeId ? (
              <FleetMemberDetailPanel
                fleetId={fleetId}
                memberId={selectedNodeId}
                onClose={() => updateSelectedMember(null)}
              />
            ) : null}
          </TabsContent>
        ) : null}

        {activeTab === "members" ? (
          <TabsContent>
            <FleetMemberPanel fleetId={fleetId} />
          </TabsContent>
        ) : null}

        {activeTab === "performance" ? (
          <TabsContent className="space-y-6">
            <section className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm">
              <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h3 className="text-xl font-semibold">Performance profile</h3>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Monitor health and output trends with synchronized telemetry.
                  </p>
                </div>
                <FleetHealthGauge fleetId={fleetId} size="lg" />
              </div>
            </section>
            <FleetPerformanceCharts fleetId={fleetId} />
          </TabsContent>
        ) : null}

        {activeTab === "controls" ? (
          <TabsContent>
            <FleetControlsPanel
              currentStatus={fleet.status}
              fleetId={fleetId}
              members={fleet.members}
            />
          </TabsContent>
        ) : null}

        {activeTab === "observers" ? (
          <TabsContent>
            <FleetObserverPanel fleetId={fleetId} />
          </TabsContent>
        ) : null}
      </Tabs>
    </div>
  );
}
