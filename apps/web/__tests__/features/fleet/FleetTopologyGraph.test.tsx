import { act, fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FleetTopologyGraph } from "@/components/features/fleet/FleetTopologyGraph";
import { renderWithProviders } from "@/test-utils/render";
import {
  sampleHealthProjection,
  sampleMembers,
  sampleTopologyVersion,
  seedFleetStores,
} from "@/__tests__/features/fleet/test-helpers";

const topologyLayoutMock = vi.hoisted(() =>
  vi.fn(() => ({
    nodes: sampleMembers.slice(0, 2).map((member, index) => ({
      id: member.id,
      type: "fleet-member",
      position: { x: index * 100, y: 0 },
      data: {
        kind: "member",
        member,
        memberId: member.id,
        role: member.role,
        health_pct: member.health_pct,
      },
    })),
    edges: [],
  })),
);

const wsMocks = vi.hoisted(() => {
  let eventHandler: ((event: { payload: unknown }) => void) | null = null;
  return {
    connect: vi.fn(),
    emit: (payload: unknown) => eventHandler?.({ payload }),
    onConnectionChange: vi.fn((handler: (state: boolean) => void) => {
      handler(true);
      return vi.fn();
    }),
    subscribe: vi.fn((_channel: string, handler: (event: { payload: unknown }) => void) => {
      eventHandler = handler;
      return vi.fn();
    }),
  };
});

vi.mock("@xyflow/react", () => ({
  Background: () => <div data-testid="graph-background" />,
  BaseEdge: ({ id }: { id: string }) => <div data-testid={`edge-${id}`} />,
  Controls: () => <div data-testid="graph-controls" />,
  Handle: () => <span />,
  MarkerType: { ArrowClosed: "arrowclosed" },
  MiniMap: () => <div data-testid="graph-minimap" />,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
  ReactFlow: ({
    nodes,
    onNodeClick,
  }: {
    nodes: Array<{ id: string; data: { health_pct: number } }>;
    onNodeClick?: (event: unknown, node: { id: string }) => void;
  }) => (
    <div data-testid="react-flow">
      <span data-testid="node-count">{nodes.length}</span>
      {nodes.map((node) => (
        <button
          key={node.id}
          data-testid={`node-${node.id}`}
          type="button"
          onClick={() => onNodeClick?.({}, { id: node.id })}
        >
          {node.id}:{node.data.health_pct}
        </button>
      ))}
    </div>
  ),
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  getSmoothStepPath: () => ["M0 0"],
}));

vi.mock("@/lib/hooks/use-fleet-topology", () => ({
  useFleetTopology: () => ({
    data: sampleTopologyVersion,
    isError: false,
    isLoading: false,
  }),
}));

vi.mock("@/lib/hooks/use-fleet-members", () => ({
  useFleetMembers: () => ({
    data: sampleMembers,
    isError: false,
    isLoading: false,
  }),
}));

vi.mock("@/lib/hooks/use-fleet-health", () => ({
  useFleetHealth: () => ({
    data: sampleHealthProjection,
    isError: false,
    isLoading: false,
  }),
}));

vi.mock("@/lib/utils/fleet-topology-layout", () => ({
  buildFleetTopologyLayout: topologyLayoutMock,
}));

vi.mock("@/lib/ws", () => ({
  wsClient: wsMocks,
}));

describe("FleetTopologyGraph", () => {
  beforeEach(() => {
    topologyLayoutMock.mockClear();
    seedFleetStores();
  });

  it("renders graph nodes, selects a node, and updates health from websocket events without re-layout", () => {
    const onNodeSelect = vi.fn();

    renderWithProviders(<FleetTopologyGraph fleetId="fleet-1" onNodeSelect={onNodeSelect} />);

    expect(screen.getByTestId("node-count")).toHaveTextContent("2");
    expect(screen.getByTestId("node-member-1")).toHaveTextContent("member-1:92");

    fireEvent.click(screen.getByTestId("node-member-1"));
    expect(onNodeSelect).toHaveBeenCalledWith("member-1");
    const callCountAfterSelection = topologyLayoutMock.mock.calls.length;

    act(() => {
      wsMocks.emit({
        member_statuses: [
          { agent_fqn: "risk:triage-lead", health_pct: 20 },
          { agent_fqn: "risk:worker-one", health_pct: 88 },
        ],
      });
    });

    expect(screen.getByTestId("node-member-1")).toHaveTextContent("member-1:20");
    expect(topologyLayoutMock).toHaveBeenCalledTimes(callCountAfterSelection);
  });
});
