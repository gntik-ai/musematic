"use client";

import "@xyflow/react/dist/style.css";

import { useEffect, useMemo } from "react";
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
import { AlertTriangle, GitBranch, Workflow } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import { useWorkflowGraph } from "@/lib/hooks/use-workflow-graph";
import { useWorkflowEditorStore } from "@/lib/stores/workflow-editor-store";
import type { WorkflowIR, WorkflowGraphNode, WorkflowStepType } from "@/types/workflows";

interface WorkflowGraphPreviewProps {
  compiledIr?: WorkflowIR | null;
  baselineYamlContent?: string | null;
  className?: string;
}

type WorkflowPreviewNode = Node<WorkflowGraphNode["data"], "step">;

const stepTypeStyles: Record<
  WorkflowStepType,
  {
    container: string;
    badge: string;
  }
> = {
  agent_task: {
    container: "border-[hsl(var(--primary)/0.35)] bg-[hsl(var(--primary)/0.10)]",
    badge: "bg-[hsl(var(--primary)/0.14)] text-[hsl(var(--primary))]",
  },
  approval_gate: {
    container: "border-[hsl(var(--warning)/0.45)] bg-[hsl(var(--warning)/0.12)]",
    badge: "bg-[hsl(var(--warning)/0.18)] text-[hsl(var(--warning))]",
  },
  conditional: {
    container: "border-[hsl(var(--brand-accent)/0.38)] bg-[hsl(var(--brand-accent)/0.12)]",
    badge: "bg-[hsl(var(--brand-accent)/0.18)] text-[hsl(var(--brand-accent))]",
  },
  compensation: {
    container:
      "border-[hsl(var(--destructive)/0.45)] bg-[hsl(var(--destructive)/0.12)]",
    badge: "bg-[hsl(var(--destructive)/0.18)] text-[hsl(var(--destructive))]",
  },
  delay: {
    container: "border-border bg-muted/70",
    badge: "bg-secondary text-secondary-foreground",
  },
  parallel_fan_in: {
    container: "border-[hsl(var(--secondary-foreground)/0.18)] bg-secondary/90",
    badge: "bg-background/80 text-secondary-foreground",
  },
  parallel_fan_out: {
    container: "border-[hsl(var(--secondary-foreground)/0.18)] bg-secondary/90",
    badge: "bg-background/80 text-secondary-foreground",
  },
  webhook_trigger: {
    container: "border-[hsl(var(--accent-foreground)/0.26)] bg-accent/90",
    badge: "bg-background/70 text-accent-foreground",
  },
};

function formatStepType(stepType: WorkflowStepType): string {
  return stepType.replace(/_/g, " ");
}

function StepPreviewNode({
  data,
  selected,
}: NodeProps<WorkflowPreviewNode>) {
  const styleConfig = data.hasValidationError
    ? {
        container:
          "border-[hsl(var(--destructive)/0.52)] bg-[hsl(var(--destructive)/0.10)] shadow-[0_0_0_1px_hsl(var(--destructive)/0.12)]",
        badge: "bg-[hsl(var(--destructive)/0.16)] text-[hsl(var(--destructive))]",
      }
    : stepTypeStyles[data.stepType];

  return (
    <div
      aria-label={`${data.label}, ${formatStepType(data.stepType)} step`}
      className={cn(
        "min-w-[248px] rounded-2xl border px-4 py-3 shadow-sm transition-shadow",
        selected ? "shadow-[0_0_0_2px_hsl(var(--ring)/0.25)]" : "shadow-none",
        styleConfig.container,
      )}
      role="img"
    >
      <Handle
        className="!h-3 !w-3 !border-2 !border-background !bg-primary"
        position={Position.Top}
        type="target"
      />
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <p className="text-sm font-semibold text-foreground">{data.label}</p>
            {data.agentFqn ? (
              <p className="text-xs text-muted-foreground">{data.agentFqn}</p>
            ) : null}
          </div>
          {data.hasValidationError ? (
            <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />
          ) : null}
        </div>
        <span
          className={cn(
            "inline-flex rounded-full px-2 py-1 text-[11px] font-medium uppercase tracking-[0.08em]",
            styleConfig.badge,
          )}
        >
          {formatStepType(data.stepType)}
        </span>
      </div>
      <Handle
        className="!h-3 !w-3 !border-2 !border-background !bg-primary"
        position={Position.Bottom}
        type="source"
      />
    </div>
  );
}

const nodeTypes = {
  step: StepPreviewNode,
} satisfies NodeTypes;

function WorkflowGraphCanvas({
  compiledIr,
  baselineYamlContent,
  className,
}: WorkflowGraphPreviewProps) {
  const yamlContent = useWorkflowEditorStore((state) => state.yamlContent);
  const validationErrors = useWorkflowEditorStore(
    (state) => state.validationErrors,
  );
  const setGraphState = useWorkflowEditorStore((state) => state.setGraphState);
  const setParseError = useWorkflowEditorStore((state) => state.setParseError);
  const { nodes, edges, parseError } = useWorkflowGraph({
    ...(compiledIr !== undefined ? { compiledIr } : {}),
    yamlContent,
    ...(baselineYamlContent !== undefined ? { baselineYamlContent } : {}),
    validationErrors,
  });

  useEffect(() => {
    setGraphState(nodes, edges);
    setParseError(parseError);
  }, [edges, nodes, parseError, setGraphState, setParseError]);

  const flowNodes = useMemo<WorkflowPreviewNode[]>(
    () =>
      nodes.map((node) => ({
        ...node,
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      })),
    [nodes],
  );

  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((edge) => ({
        ...edge,
        animated: false,
        markerEnd: {
          type: MarkerType.ArrowClosed,
        },
        style: {
          stroke: "hsl(var(--border))",
          strokeWidth: 1.5,
        },
      })),
    [edges],
  );

  const isEmpty =
    (yamlContent ?? "").trim().length === 0 && (compiledIr?.steps.length ?? 0) === 0;

  if (isEmpty) {
    return (
      <div
        className={cn(
          "flex h-[560px] flex-col items-center justify-center rounded-2xl border border-dashed border-border/70 bg-card/70 px-6 text-center",
          className,
        )}
      >
        <Workflow className="h-10 w-10 text-muted-foreground" />
        <h3 className="mt-4 text-lg font-semibold text-foreground">
          No workflow graph yet
        </h3>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Start typing YAML on the left and the DAG preview will render here.
        </p>
      </div>
    );
  }

  return (
    <div
        className={cn(
          "flex h-[560px] flex-col gap-3 rounded-2xl border border-border/60 bg-card/80 p-3 shadow-sm",
          className,
        )}
    >
      <div className="flex items-center justify-between rounded-xl border border-border/60 bg-background/60 px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <GitBranch className="h-4 w-4 text-[hsl(var(--brand-accent))]" />
          Workflow graph preview
        </div>
        <span className="text-xs text-muted-foreground">
          {flowNodes.length} steps, {flowEdges.length} dependencies
        </span>
      </div>

      {parseError ? (
        <Alert variant="destructive">
          <AlertTitle>Graph preview unavailable</AlertTitle>
          <AlertDescription>{parseError}</AlertDescription>
        </Alert>
      ) : null}

      <div className="surface-grid min-h-0 flex-1 overflow-hidden rounded-2xl border border-border/60 bg-background/80">
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
          zoomOnPinch
        >
          <MiniMap
            className="!rounded-xl !border !border-border/70 !bg-card/95"
            nodeColor={(node) =>
              node.data?.hasValidationError
                ? "hsl(var(--destructive))"
                : "hsl(var(--primary))"
            }
            pannable
            zoomable
          />
          <Controls className="!border !border-border/70 !bg-card/95 !shadow-sm" />
          <Background color="hsl(var(--border) / 0.6)" gap={20} size={1} />
        </ReactFlow>
      </div>
    </div>
  );
}

export function WorkflowGraphPreview(props: WorkflowGraphPreviewProps) {
  return (
    <ReactFlowProvider>
      <WorkflowGraphCanvas {...props} />
    </ReactFlowProvider>
  );
}
