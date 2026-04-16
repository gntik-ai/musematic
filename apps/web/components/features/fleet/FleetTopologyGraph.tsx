"use client";

import "@xyflow/react/dist/style.css";

import { useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
} from "@xyflow/react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { ConnectionStatusBanner } from "@/components/features/home/ConnectionStatusBanner";
import { CommunicationEdge } from "@/components/features/fleet/CommunicationEdge";
import { FleetMemberNode } from "@/components/features/fleet/FleetMemberNode";
import { useFleetHealth } from "@/lib/hooks/use-fleet-health";
import { useFleetMembers } from "@/lib/hooks/use-fleet-members";
import { useFleetTopology } from "@/lib/hooks/use-fleet-topology";
import { useTopologyViewportStore } from "@/lib/stores/use-topology-viewport-store";
import { getFleetHealthTone } from "@/lib/types/fleet";
import { buildFleetTopologyLayout, type FleetGraphNodeData } from "@/lib/utils/fleet-topology-layout";
import { wsClient } from "@/lib/ws";

interface FleetTopologyGraphProps {
  fleetId: string;
  onNodeSelect?: (memberId: string | null) => void;
}

function extractMemberHealthMap(payload: unknown): Map<string, number> {
  if (!payload || typeof payload !== "object") {
    return new Map();
  }

  const candidate =
    "health_projection" in payload && typeof payload.health_projection === "object"
      ? payload.health_projection
      : payload;

  if (!candidate || typeof candidate !== "object" || !("member_statuses" in candidate)) {
    return new Map();
  }

  const memberStatuses = (candidate as { member_statuses?: unknown }).member_statuses;
  if (!Array.isArray(memberStatuses)) {
    return new Map();
  }

  return new Map(
    memberStatuses
      .filter((entry): entry is { agent_fqn: string; health_pct: number } => {
        return (
          typeof entry === "object" &&
          entry !== null &&
          typeof (entry as { agent_fqn?: unknown }).agent_fqn === "string" &&
          typeof (entry as { health_pct?: unknown }).health_pct === "number"
        );
      })
      .map((entry) => [entry.agent_fqn, entry.health_pct]),
  );
}

export function FleetTopologyGraph({
  fleetId,
  onNodeSelect,
}: FleetTopologyGraphProps) {
  const topologyQuery = useFleetTopology(fleetId);
  const membersQuery = useFleetMembers(fleetId);
  const healthQuery = useFleetHealth(fleetId);
  const viewport = useTopologyViewportStore((state) => state.viewport);
  const expandedGroups = useTopologyViewportStore((state) => state.expandedGroups);
  const selectedNodeId = useTopologyViewportStore((state) => state.selectedNodeId);
  const reset = useTopologyViewportStore((state) => state.reset);
  const setViewport = useTopologyViewportStore((state) => state.setViewport);
  const selectNode = useTopologyViewportStore((state) => state.selectNode);
  const toggleGroup = useTopologyViewportStore((state) => state.toggleGroup);
  const [isConnected, setIsConnected] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [liveHealthByFqn, setLiveHealthByFqn] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    reset();
    setLiveHealthByFqn(new Map());
  }, [fleetId, reset]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(max-width: 767px)");
    const handleChange = () => setIsMobile(mediaQuery.matches);
    handleChange();
    mediaQuery.addEventListener("change", handleChange);

    return () => {
      mediaQuery.removeEventListener("change", handleChange);
    };
  }, []);

  useEffect(() => {
    wsClient.connect();

    const unsubscribeConnection = wsClient.onConnectionChange(setIsConnected);
    const unsubscribeFleet = wsClient.subscribe(`fleet:${fleetId}`, (event) => {
      const nextMap = extractMemberHealthMap(event.payload);
      if (nextMap.size === 0) {
        return;
      }

      setLiveHealthByFqn((current) => {
        const merged = new Map(current);
        nextMap.forEach((value, key) => merged.set(key, value));
        return merged;
      });
    });

    return () => {
      unsubscribeConnection();
      unsubscribeFleet();
    };
  }, [fleetId]);

  const members = membersQuery.data ?? [];
  const liveHealth = useMemo(() => {
    const seed = new Map<string, number>(
      members.map((member) => [member.agent_fqn, member.health_pct]),
    );
    if (healthQuery.data) {
      healthQuery.data.member_statuses.forEach((member) => {
        seed.set(member.agent_fqn, member.health_pct);
      });
    }
    liveHealthByFqn.forEach((value, key) => seed.set(key, value));
    return seed;
  }, [healthQuery.data, liveHealthByFqn, members]);

  const positionedGraph = useMemo(
    () =>
      buildFleetTopologyLayout({
        members,
        topology: topologyQuery.data?.config,
        topologyType: topologyQuery.data?.topology_type ?? "hierarchical",
        selectedNodeId,
        expandedGroups,
      }),
    [expandedGroups, members, selectedNodeId, topologyQuery.data],
  );

  const nodes = useMemo<Node<FleetGraphNodeData>[]>(() => {
    return positionedGraph.nodes.map((node) => {
      if (node.data.kind === "member" && node.data.member) {
        return {
          ...node,
          data: {
            ...node.data,
            health_pct: liveHealth.get(node.data.member.agent_fqn) ?? node.data.health_pct,
          },
        };
      }

      if (node.data.kind === "group" && node.data.role) {
        const groupMembers = members.filter((member) => member.role === node.data.role);
        const groupHealth =
          groupMembers.length === 0
            ? node.data.health_pct
            : Math.round(
                groupMembers.reduce(
                  (sum, member) => sum + (liveHealth.get(member.agent_fqn) ?? member.health_pct),
                  0,
                ) / groupMembers.length,
              );

        return {
          ...node,
          data: {
            ...node.data,
            health_pct: groupHealth,
            label: `${node.data.role} group (${node.data.memberCount ?? 0}) · ${groupHealth}%`,
          },
        };
      }

      return node;
    });
  }, [liveHealth, members, positionedGraph.nodes]);

  const edges = useMemo<Edge[]>(
    () =>
      positionedGraph.edges.map((edge) =>
        edge.data?.relationship === "delegation"
          ? {
              ...edge,
              animated: false,
              markerEnd: { type: MarkerType.ArrowClosed },
            }
          : {
              ...edge,
              animated: edge.data?.relationship === "communication",
            },
      ),
    [positionedGraph.edges],
  );

  if (topologyQuery.isLoading || membersQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-16 rounded-3xl" />
        <Skeleton className="h-[680px] rounded-[2rem]" />
      </div>
    );
  }

  if (topologyQuery.isError || membersQuery.isError) {
    return (
      <EmptyState
        description="The fleet topology could not be loaded."
        title="Topology unavailable"
      />
    );
  }

  if (members.length === 0) {
    return (
      <EmptyState
        description="Add members to this fleet to render its topology."
        title="No members yet"
      />
    );
  }

  if (isMobile) {
    return (
      <div className="space-y-4">
        <ConnectionStatusBanner isConnected={isConnected} />
        <div className="grid gap-3">
          {members.map((member) => {
            const health = liveHealth.get(member.agent_fqn) ?? member.health_pct;
            const tone = getFleetHealthTone(health);
            const ringClassName =
              tone === "healthy"
                ? "border-emerald-500/40"
                : tone === "warning"
                  ? "border-amber-500/40"
                  : "border-rose-500/40";

            return (
              <button
                key={member.id}
                className={`rounded-3xl border bg-card/80 p-4 text-left ${ringClassName}`}
                type="button"
                onClick={() => {
                  selectNode(member.id);
                  onNodeSelect?.(member.id);
                }}
              >
                <p className="font-medium">{member.agent_name}</p>
                <p className="mt-1 text-xs text-muted-foreground">{member.agent_fqn}</p>
                <p className="mt-3 text-sm">{member.role} · {health}% health</p>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ConnectionStatusBanner isConnected={isConnected} />
      <div className="overflow-hidden rounded-[2rem] border border-border/70 bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.12),transparent_24%),linear-gradient(160deg,hsl(var(--card))_0%,hsl(var(--muted)/0.48)_100%)]">
        <div className="flex items-center justify-between border-b border-border/70 bg-background/75 px-5 py-4 backdrop-blur">
          <div>
            <h3 className="text-lg font-semibold">Topology view</h3>
            <p className="text-sm text-muted-foreground">
              Click a member to inspect it, or click a collapsed role group to expand it.
            </p>
          </div>
        </div>
        <div className="h-[680px]">
          <ReactFlowProvider>
            <ReactFlow
              defaultViewport={viewport ?? { x: 0, y: 0, zoom: 0.9 }}
              edgeTypes={{ "fleet-communication": CommunicationEdge }}
              edges={edges}
              fitView={!viewport}
              minZoom={0.35}
              nodeTypes={{ "fleet-member": FleetMemberNode }}
              nodes={nodes}
              onMoveEnd={(_event, nextViewport) => {
                setViewport(nextViewport);
              }}
              onNodeClick={(_event, node) => {
                if (node.id.startsWith("group:")) {
                  toggleGroup(node.id);
                  return;
                }

                selectNode(node.id);
                onNodeSelect?.(node.id);
              }}
            >
              <MiniMap
                pannable
                zoomable
                nodeColor={(node) => {
                  const tone = getFleetHealthTone((node.data as FleetGraphNodeData).health_pct);
                  if (tone === "healthy") {
                    return "hsl(var(--brand-primary))";
                  }
                  if (tone === "warning") {
                    return "hsl(var(--warning))";
                  }
                  return "hsl(var(--destructive))";
                }}
              />
              <Controls showInteractive />
              <Background gap={24} />
            </ReactFlow>
          </ReactFlowProvider>
        </div>
      </div>
    </div>
  );
}
