"use client";

import "@xyflow/react/dist/style.css";

import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
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
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import type { VisibilityGrant } from "@/lib/schemas/workspace-owner";
import { GrantDetailPanel, type GrantDetail } from "./GrantDetailPanel";

interface VisibilityNodeData extends Record<string, unknown> {
  label: ReactNode;
}

const NODE_WIDTH = 230;
const NODE_HEIGHT = 92;

export function VisibilityGraph({ grant }: { grant: VisibilityGrant }) {
  const t = useTranslations("workspaces.visibility");
  const [selectedGrant, setSelectedGrant] = useState<GrantDetail | null>(null);
  const { nodes, edges, details } = useMemo(() => buildGraph(grant, t), [grant, t]);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="overflow-hidden rounded-lg border">
        <div className="flex items-center justify-between border-b p-3">
          <div>
            <h2 className="text-base font-semibold">{t("graph")}</h2>
            <p className="text-xs text-muted-foreground">{t("graphSubtitle")}</p>
          </div>
          <Badge variant={edges.length ? "secondary" : "outline"}>
            {edges.length ? t("grantsConfigured") : t("denyAll")}
          </Badge>
        </div>
        <div className="h-[620px]">
          <ReactFlowProvider>
            <ReactFlow
              edges={edges}
              fitView
              nodes={nodes}
              onEdgeClick={(_, edge) => setSelectedGrant(details.get(edge.id) ?? null)}
            >
              <MiniMap pannable zoomable />
              <Controls />
              <Background gap={28} />
            </ReactFlow>
          </ReactFlowProvider>
        </div>
      </div>
      <GrantDetailPanel grant={selectedGrant} />
    </div>
  );
}

function buildGraph(
  grant: VisibilityGrant,
  t: ReturnType<typeof useTranslations>,
): {
  nodes: Node<VisibilityNodeData>[];
  edges: Edge[];
  details: Map<string, GrantDetail>;
} {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 48, ranksep: 96 });
  const workspaceNode = `workspace:${grant.workspace_id}`;
  const patterns = [...grant.visibility_agents, ...grant.visibility_tools];
  graph.setNode(workspaceNode, { width: NODE_WIDTH, height: NODE_HEIGHT });

  const workspaceEntry: Node<VisibilityNodeData> = {
    id: workspaceNode,
    position: { x: 0, y: 0 },
    data: {
      label: (
        <NodeLabel
          title={t("currentWorkspace")}
          subtitle={patterns.length === 0 ? t("denyAll") : grant.workspace_id}
        />
      ),
    },
    style: nodeStyle("hsl(var(--background))"),
  };
  const nodes: Node<VisibilityNodeData>[] = [workspaceEntry];
  const edges: Edge[] = [];
  const details = new Map<string, GrantDetail>();

  patterns.forEach((pattern, index) => {
    const nodeId = `grant:${index}`;
    const edgeId = `${workspaceNode}->${nodeId}`;
    graph.setNode(nodeId, { width: NODE_WIDTH, height: NODE_HEIGHT });
    graph.setEdge(workspaceNode, nodeId);
    nodes.push({
      id: nodeId,
      position: { x: 0, y: 0 },
      data: { label: <NodeLabel title={pattern} subtitle={t("grantGiven")} /> },
      style: nodeStyle("hsl(var(--muted))"),
    });
    edges.push({ id: edgeId, source: workspaceNode, target: nodeId, label: t("allows") });
    details.set(edgeId, { direction: "given", label: t("workspaceGrant"), pattern });
  });

  dagre.layout(graph);
  return {
    nodes: nodes.map((node) => {
      const position = graph.node(node.id) as { x: number; y: number } | undefined;
      return {
        ...node,
        position: {
          x: (position?.x ?? 0) - NODE_WIDTH / 2,
          y: (position?.y ?? 0) - NODE_HEIGHT / 2,
        },
      };
    }),
    edges,
    details,
  };
}

function NodeLabel({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="space-y-1 text-left">
      <p className="truncate text-sm font-medium">{title}</p>
      <p className="truncate text-xs text-muted-foreground">{subtitle}</p>
    </div>
  );
}

function nodeStyle(background: string): CSSProperties {
  return {
    width: NODE_WIDTH,
    borderRadius: 8,
    border: "1px solid hsl(var(--border))",
    background,
    padding: 12,
  };
}
