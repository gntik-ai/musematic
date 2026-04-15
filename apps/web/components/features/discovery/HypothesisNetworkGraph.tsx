"use client";

import "@xyflow/react/dist/style.css";

import { useMemo, useState } from "react";
import dagre from "@dagrejs/dagre";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
} from "@xyflow/react";
import { EmptyState } from "@/components/shared/EmptyState";
import { ClusterLegend, clusterColor } from "@/components/features/discovery/ClusterLegend";
import { NodeDetailPanel } from "@/components/features/discovery/NodeDetailPanel";
import { cn } from "@/lib/utils";
import type {
  DiscoveryCluster,
  DiscoveryHypothesis,
} from "@/lib/hooks/use-discovery-network";

interface HypothesisNetworkGraphProps {
  hypotheses: DiscoveryHypothesis[];
  clusters: DiscoveryCluster[];
  similarityThreshold?: number;
}

interface HypothesisNodeData extends Record<string, unknown> {
  hypothesis: DiscoveryHypothesis;
}

const NODE_WIDTH = 260;
const NODE_HEIGHT = 116;

export function HypothesisNetworkGraph({
  hypotheses,
  clusters,
  similarityThreshold = 0.72,
}: HypothesisNetworkGraphProps) {
  const [selectedCluster, setSelectedCluster] = useState<string | null>(null);
  const [selectedHypothesis, setSelectedHypothesis] = useState<DiscoveryHypothesis | null>(null);

  const visibleHypotheses = useMemo(
    () =>
      selectedCluster
        ? hypotheses.filter((hypothesis) => hypothesis.cluster_id === selectedCluster)
        : hypotheses,
    [hypotheses, selectedCluster],
  );

  const { nodes, edges } = useMemo(
    () => buildGraph(visibleHypotheses, clusters, similarityThreshold),
    [visibleHypotheses, clusters, similarityThreshold],
  );

  if (hypotheses.length === 0) {
    return (
      <EmptyState
        description="Run a discovery cycle and compute proximity to populate this network."
        title="No hypotheses yet"
      />
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="overflow-hidden rounded-[2rem] border bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-accent)/0.16),transparent_30%),linear-gradient(135deg,hsl(var(--background)),hsl(var(--muted)/0.55))] shadow-sm">
        <div className="flex flex-col gap-3 border-b bg-background/70 p-4 backdrop-blur md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-lg font-semibold">Hypothesis landscape</h2>
            <p className="text-sm text-muted-foreground">
              Cluster-coloured Elo network with inferred similarity edges.
            </p>
          </div>
          <ClusterLegend
            clusters={clusters}
            selectedCluster={selectedCluster}
            onSelectCluster={setSelectedCluster}
          />
        </div>
        <div className="h-[680px]">
          <ReactFlowProvider>
            <ReactFlow
              edges={edges}
              fitView
              nodes={nodes}
              onNodeClick={(_, node) => {
                setSelectedHypothesis((node.data as HypothesisNodeData).hypothesis);
              }}
            >
              <MiniMap pannable zoomable />
              <Controls />
              <Background gap={28} />
            </ReactFlow>
          </ReactFlowProvider>
        </div>
      </div>
      <NodeDetailPanel hypothesis={selectedHypothesis} />
    </div>
  );
}

function buildGraph(
  hypotheses: DiscoveryHypothesis[],
  clusters: DiscoveryCluster[],
  similarityThreshold: number,
): { nodes: Node<HypothesisNodeData>[]; edges: Edge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 64, ranksep: 96 });

  const clusterByLabel = new Map(clusters.map((cluster) => [cluster.cluster_label, cluster]));
  const nodes: Node<HypothesisNodeData>[] = hypotheses.map((hypothesis) => {
    graph.setNode(hypothesis.hypothesis_id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    return {
      id: hypothesis.hypothesis_id,
      type: "default",
      data: {
        label: hypothesis.title,
        hypothesis,
      },
      position: { x: 0, y: 0 },
      className: "discovery-network-node",
      style: {
        width: NODE_WIDTH,
        borderRadius: 24,
        border: "1px solid hsl(var(--border))",
        background: "hsl(var(--background) / 0.95)",
        boxShadow: "0 18px 45px hsl(var(--foreground) / 0.08)",
        padding: 12,
      },
    };
  });

  const edges: Edge[] = [];
  for (const cluster of clusters) {
    const clusterHypotheses = hypotheses.filter((hypothesis) =>
      cluster.hypothesis_ids.includes(hypothesis.hypothesis_id),
    );
    if (cluster.density_metric < similarityThreshold) {
      continue;
    }
    for (let index = 0; index < clusterHypotheses.length - 1; index += 1) {
      const source = clusterHypotheses[index];
      const target = clusterHypotheses[index + 1];
      if (!source || !target) {
        continue;
      }
      graph.setEdge(source.hypothesis_id, target.hypothesis_id);
      edges.push({
        id: `${source.hypothesis_id}-${target.hypothesis_id}`,
        source: source.hypothesis_id,
        target: target.hypothesis_id,
        animated: cluster.classification === "over_explored",
        label: cluster.density_metric.toFixed(2),
      });
    }
  }

  dagre.layout(graph);
  const positionedNodes = nodes.map((node) => {
    const position = graph.node(node.id) as { x: number; y: number } | undefined;
    const hypothesis = node.data.hypothesis;
    const cluster = hypothesis.cluster_id ? clusterByLabel.get(hypothesis.cluster_id) : null;
    const colorClass = clusterColor(cluster?.cluster_label ?? hypothesis.cluster_id);
    return {
      ...node,
      position: {
        x: (position?.x ?? 0) - NODE_WIDTH / 2,
        y: (position?.y ?? 0) - NODE_HEIGHT / 2,
      },
      data: {
        ...node.data,
        label: (
          <div className="space-y-2 text-left">
            <div className="flex items-center gap-2">
              <span className={cn("h-3 w-3 rounded-full", colorClass)} />
              <span className="text-xs font-medium text-muted-foreground">
                {hypothesis.cluster_id ?? "unclustered"}
              </span>
            </div>
            <p className="line-clamp-2 text-sm font-semibold text-foreground">
              {hypothesis.title}
            </p>
            <p className="text-xs text-muted-foreground">
              Elo {hypothesis.elo_score?.toFixed(1) ?? "n/a"} · confidence{" "}
              {Math.round(hypothesis.confidence * 100)}%
            </p>
          </div>
        ),
      },
    };
  });

  return { nodes: positionedNodes, edges };
}
