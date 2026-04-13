"use client";

import "@xyflow/react/dist/style.css";

import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import { EmptyState } from "@/components/shared/EmptyState";
import { useWorkflowGraph } from "@/lib/hooks/use-workflow-graph";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import { cn, toTitleCase } from "@/lib/utils";
import type { StepStatus } from "@/types/execution";
import type { WorkflowIR, WorkflowStepType } from "@/types/workflows";

type ExecutionGraphNodeData = {
  stepId: string;
  label: string;
  stepType: WorkflowStepType;
  status: StepStatus;
  selected: boolean;
};

type ExecutionFlowNode = Node<ExecutionGraphNodeData, "execution-step">;

const statusStyles: Record<
  StepStatus,
  { container: string; badge: string; label: string }
> = {
  pending: {
    container: "border-border bg-muted/60",
    badge: "bg-background/80 text-muted-foreground",
    label: "Pending",
  },
  running: {
    container: "border-[hsl(var(--primary)/0.45)] bg-[hsl(var(--primary)/0.10)]",
    badge: "bg-[hsl(var(--primary)/0.16)] text-[hsl(var(--primary))]",
    label: "Running",
  },
  completed: {
    container: "border-[hsl(var(--brand-accent)/0.42)] bg-[hsl(var(--brand-accent)/0.10)]",
    badge: "bg-[hsl(var(--brand-accent)/0.16)] text-[hsl(var(--brand-accent))]",
    label: "Completed",
  },
  failed: {
    container: "border-[hsl(var(--destructive)/0.55)] bg-[hsl(var(--destructive)/0.10)]",
    badge: "bg-[hsl(var(--destructive)/0.18)] text-[hsl(var(--destructive))]",
    label: "Failed",
  },
  skipped: {
    container: "border-border bg-secondary/80",
    badge: "bg-background/80 text-muted-foreground",
    label: "Skipped",
  },
  waiting_for_approval: {
    container: "border-[hsl(var(--warning)/0.55)] bg-[hsl(var(--warning)/0.12)]",
    badge: "bg-[hsl(var(--warning)/0.18)] text-[hsl(var(--warning))]",
    label: "Awaiting approval",
  },
  canceled: {
    container: "border-border bg-muted/75",
    badge: "bg-background/80 text-muted-foreground",
    label: "Canceled",
  },
};

function moveFocusBetweenNodes(
  currentStepId: string,
  direction: 1 | -1,
) {
  const elements = Array.from(
    document.querySelectorAll<HTMLButtonElement>("[data-execution-step-node]"),
  );
  const currentIndex = elements.findIndex(
    (element) => element.dataset.executionStepNode === currentStepId,
  );

  if (currentIndex === -1) {
    return;
  }

  const nextElement = elements[currentIndex + direction];
  nextElement?.focus();
}

function ExecutionStepNode({
  data,
}: NodeProps<ExecutionFlowNode>) {
  const selectStep = useExecutionMonitorStore((state) => state.selectStep);
  const styleConfig = statusStyles[data.status];

  return (
    <button
      aria-label={`${data.label}, ${styleConfig.label}`}
      className={cn(
        "min-w-[248px] rounded-2xl border px-4 py-3 text-left shadow-sm transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        styleConfig.container,
        data.selected && "shadow-[0_0_0_2px_hsl(var(--ring)/0.24)]",
      )}
      data-execution-step-node={data.stepId}
      onClick={() => {
        selectStep(data.stepId);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectStep(data.stepId);
        }

        if (event.key === "ArrowRight" || event.key === "ArrowDown") {
          event.preventDefault();
          moveFocusBetweenNodes(data.stepId, 1);
        }

        if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
          event.preventDefault();
          moveFocusBetweenNodes(data.stepId, -1);
        }
      }}
      role="img"
      type="button"
    >
      <Handle
        className="!h-3 !w-3 !border-2 !border-background !bg-primary"
        position={Position.Top}
        type="target"
      />
      <div className="space-y-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold text-foreground">{data.label}</p>
          <p className="text-xs text-muted-foreground">
            {toTitleCase(data.stepType)}
          </p>
        </div>
        <span
          className={cn(
            "inline-flex rounded-full px-2 py-1 text-[11px] font-medium uppercase tracking-[0.08em]",
            styleConfig.badge,
          )}
        >
          {styleConfig.label}
        </span>
      </div>
      <Handle
        className="!h-3 !w-3 !border-2 !border-background !bg-primary"
        position={Position.Bottom}
        type="source"
      />
    </button>
  );
}

const nodeTypes = {
  "execution-step": ExecutionStepNode,
} satisfies NodeTypes;

function ExecutionGraphCanvas({
  compiledIr,
}: {
  compiledIr: WorkflowIR;
}) {
  const stepStatuses = useExecutionMonitorStore((state) => state.stepStatuses);
  const selectedStepId = useExecutionMonitorStore((state) => state.selectedStepId);
  const { nodes, edges } = useWorkflowGraph({
    compiledIr,
    yamlContent: "",
  });

  const flowNodes = useMemo<ExecutionFlowNode[]>(
    () =>
      nodes.map((node) => ({
        ...node,
        type: "execution-step",
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        data: {
          stepId: node.data.stepId,
          label: node.data.label,
          stepType: node.data.stepType,
          status: stepStatuses[node.data.stepId] ?? "pending",
          selected: selectedStepId === node.data.stepId,
        },
      })),
    [nodes, selectedStepId, stepStatuses],
  );

  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => ({
        ...edge,
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: {
          stroke: "hsl(var(--border))",
          strokeWidth: 1.5,
        },
      })),
    [edges],
  );

  if (flowNodes.length === 0) {
    return (
      <EmptyState
        description="No workflow steps were available for this execution."
        title="Execution graph unavailable"
      />
    );
  }

  return (
    <div className="surface-grid h-full min-h-[420px] overflow-hidden rounded-3xl border border-border/70 bg-background/80">
      <ReactFlow
        edges={flowEdges}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        nodes={flowNodes}
        nodeTypes={nodeTypes}
        nodesConnectable={false}
        nodesDraggable={false}
        panOnDrag
        proOptions={{ hideAttribution: true }}
      >
        <MiniMap
          className="!rounded-xl !border !border-border/70 !bg-card/95"
          nodeColor={(node) => {
            const status = (node.data as ExecutionGraphNodeData).status;
            if (status === "failed") return "hsl(var(--destructive))";
            if (status === "completed") return "hsl(var(--brand-accent))";
            if (status === "waiting_for_approval") return "hsl(var(--warning))";
            if (status === "running") return "hsl(var(--primary))";
            return "hsl(var(--border))";
          }}
          pannable
          zoomable
        />
        <Controls className="!border !border-border/70 !bg-card/95 !shadow-sm" />
        <Background color="hsl(var(--border) / 0.6)" gap={20} size={1} />
      </ReactFlow>
    </div>
  );
}

export function ExecutionGraph({
  compiledIr,
}: {
  compiledIr: WorkflowIR;
}) {
  return (
    <ReactFlowProvider>
      <ExecutionGraphCanvas compiledIr={compiledIr} />
    </ReactFlowProvider>
  );
}
