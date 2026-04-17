import dagre from "@dagrejs/dagre";
import type { Edge, Node } from "@xyflow/react";
import type {
  FleetMember,
  FleetMemberRole,
  FleetTopologyType,
  TopologyConfig,
} from "@/lib/types/fleet";

const MEMBER_NODE_WIDTH = 248;
const MEMBER_NODE_HEIGHT = 110;
const GROUP_NODE_WIDTH = 280;
const GROUP_NODE_HEIGHT = 92;

export interface FleetGraphNodeData extends Record<string, unknown> {
  kind: "member" | "group";
  memberId?: string;
  role?: FleetMemberRole;
  memberCount?: number;
  member?: FleetMember;
  health_pct: number;
  selected?: boolean;
}

export interface BuildFleetTopologyLayoutOptions {
  members: FleetMember[];
  topology: TopologyConfig | null | undefined;
  topologyType: FleetTopologyType;
  selectedNodeId?: string | null;
  expandedGroups?: string[];
}

interface GraphNodeMeta {
  id: string;
  width: number;
  height: number;
  data: FleetGraphNodeData;
}

function getRankDirection(topologyType: FleetTopologyType): "TB" | "LR" {
  return topologyType === "peer_to_peer" ? "LR" : "TB";
}

function average(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }

  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function getGroupId(role: FleetMemberRole): string {
  return `group:${role}`;
}

function collapseMembersByRole(
  members: FleetMember[],
  expandedGroups: string[],
): {
  nodes: GraphNodeMeta[];
  memberToRenderable: Map<string, string>;
} {
  const membersByRole = new Map<FleetMemberRole, FleetMember[]>();

  for (const member of members) {
    const current = membersByRole.get(member.role) ?? [];
    current.push(member);
    membersByRole.set(member.role, current);
  }

  const nodes: GraphNodeMeta[] = [];
  const memberToRenderable = new Map<string, string>();

  for (const [role, roleMembers] of membersByRole) {
    const groupId = getGroupId(role);
    const shouldCollapse = members.length > 50 && roleMembers.length > 1 && !expandedGroups.includes(groupId);

    if (!shouldCollapse) {
      for (const member of roleMembers) {
        nodes.push({
          id: member.id,
          width: MEMBER_NODE_WIDTH,
          height: MEMBER_NODE_HEIGHT,
          data: {
            kind: "member",
            member,
            memberId: member.id,
            role: member.role,
            health_pct: member.health_pct,
          },
        });
        memberToRenderable.set(member.id, member.id);
      }
      continue;
    }

    nodes.push({
      id: groupId,
      width: GROUP_NODE_WIDTH,
      height: GROUP_NODE_HEIGHT,
      data: {
        kind: "group",
        role,
        memberCount: roleMembers.length,
        health_pct: average(roleMembers.map((member) => member.health_pct)),
      },
    });

    for (const member of roleMembers) {
      memberToRenderable.set(member.id, groupId);
    }
  }

  return { nodes, memberToRenderable };
}

export function buildFleetTopologyLayout({
  members,
  topology,
  topologyType,
  selectedNodeId = null,
  expandedGroups = [],
}: BuildFleetTopologyLayoutOptions): {
  nodes: Node<FleetGraphNodeData>[];
  edges: Edge[];
} {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: getRankDirection(topologyType),
    ranksep: topologyType === "peer_to_peer" ? 116 : 92,
    nodesep: 48,
    marginx: 36,
    marginy: 36,
  });

  const topologyNodes = topology?.nodes ?? members.map((member) => ({
    id: member.id,
    agent_fqn: member.agent_fqn,
    role: member.role,
  }));
  const topologyEdges = topology?.edges ?? [];
  const memberById = new Map(members.map((member) => [member.id, member]));
  const topologyMembers = topologyNodes
    .map((node) => memberById.get(node.id))
    .filter((member): member is FleetMember => Boolean(member));
  const memberSet = topologyMembers.length > 0 ? topologyMembers : members;
  const { nodes: graphNodes, memberToRenderable } = collapseMembersByRole(
    memberSet,
    expandedGroups,
  );

  for (const node of graphNodes) {
    graph.setNode(node.id, { width: node.width, height: node.height });
  }

  const edgeIds = new Set<string>();
  const edges: Edge[] = [];

  for (const edge of topologyEdges) {
    const source = memberToRenderable.get(edge.source) ?? edge.source;
    const target = memberToRenderable.get(edge.target) ?? edge.target;

    if (source === target) {
      continue;
    }

    const edgeId = `${source}:${target}:${edge.type}`;
    if (edgeIds.has(edgeId)) {
      continue;
    }

    edgeIds.add(edgeId);
    graph.setEdge(source, target);
    edges.push({
      id: edgeId,
      source,
      target,
      type: "fleet-communication",
      data: {
        relationship: edge.type,
      },
    });
  }

  dagre.layout(graph);

  return {
    nodes: graphNodes.map((node) => {
      const position = graph.node(node.id) as { x: number; y: number } | undefined;
      return {
        id: node.id,
        type: node.data.kind === "group" ? "default" : "fleet-member",
        position: {
          x: (position?.x ?? 0) - node.width / 2,
          y: (position?.y ?? 0) - node.height / 2,
        },
      data: {
        ...node.data,
        ...(node.data.kind === "group"
          ? {
              label: `${node.data.role} group (${node.data.memberCount ?? 0})`,
            }
          : {}),
        selected:
          node.data.kind === "member"
            ? node.data.memberId === selectedNodeId
            : node.id === selectedNodeId,
      },
        style:
          node.data.kind === "group"
            ? {
                width: GROUP_NODE_WIDTH,
                minHeight: GROUP_NODE_HEIGHT,
                borderRadius: 24,
                border: "1px solid hsl(var(--border))",
                background:
                  "linear-gradient(160deg, hsl(var(--card)) 0%, hsl(var(--muted) / 0.7) 100%)",
              }
            : {
                width: MEMBER_NODE_WIDTH,
              },
      };
    }),
    edges,
  };
}
