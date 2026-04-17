"use client";

import { useMemo } from "react";
import dagre from "@dagrejs/dagre";
import { toTitleCase } from "@/lib/utils";
import type {
  ValidationError,
  WorkflowGraphEdge,
  WorkflowGraphNode,
  WorkflowIR,
  WorkflowIRStep,
  WorkflowStepType,
  WorkflowTrigger,
} from "@/types/workflows";

const NODE_WIDTH = 248;
const NODE_HEIGHT = 92;

interface StepLineRange {
  start: number;
  end: number;
}

interface ParsedWorkflowDefinition {
  workflowIr: WorkflowIR | null;
  parseError: string | null;
  stepLineRanges: Map<string, StepLineRange>;
}

export interface UseWorkflowGraphOptions {
  compiledIr?: WorkflowIR | null | undefined;
  yamlContent?: string | null | undefined;
  baselineYamlContent?: string | null | undefined;
  validationErrors?: ValidationError[] | undefined;
}

export interface WorkflowGraphResult {
  nodes: WorkflowGraphNode[];
  edges: WorkflowGraphEdge[];
  parseError: string | null;
}

function unquote(value: string): string {
  return value.replace(/^["']|["']$/g, "").trim();
}

function parseInlineArray(value: string): string[] {
  const normalized = value.trim();

  if (normalized.length === 0 || normalized === "[]") {
    return [];
  }

  if (!normalized.startsWith("[") || !normalized.endsWith("]")) {
    return [unquote(normalized)];
  }

  return normalized
    .slice(1, -1)
    .split(",")
    .map((entry) => unquote(entry))
    .filter(Boolean);
}

function detectCycle(steps: WorkflowIRStep[]): string | null {
  const stepMap = new Map(steps.map((step) => [step.id, step]));
  const visited = new Set<string>();
  const inStack = new Set<string>();
  const path: string[] = [];

  const visit = (stepId: string): string | null => {
    if (inStack.has(stepId)) {
      const cycleStart = path.indexOf(stepId);
      const cyclePath = [...path.slice(cycleStart), stepId].join(" -> ");
      return `Circular dependency detected: ${cyclePath}`;
    }

    if (visited.has(stepId)) {
      return null;
    }

    visited.add(stepId);
    inStack.add(stepId);
    path.push(stepId);

    for (const dependencyId of stepMap.get(stepId)?.dependencies ?? []) {
      const result = visit(dependencyId);
      if (result) {
        return result;
      }
    }

    path.pop();
    inStack.delete(stepId);
    return null;
  };

  for (const step of steps) {
    const cycleError = visit(step.id);
    if (cycleError) {
      return cycleError;
    }
  }

  return null;
}

function parseWorkflowYaml(yamlContent: string): ParsedWorkflowDefinition {
  const trimmedContent = yamlContent.trim();
  if (trimmedContent.length === 0) {
    return {
      workflowIr: null,
      parseError: null,
      stepLineRanges: new Map(),
    };
  }

  const lines = yamlContent.split(/\r?\n/);
  const steps: WorkflowIRStep[] = [];
  const stepLineRanges = new Map<string, StepLineRange>();
  const triggers: WorkflowTrigger[] = [];

  let currentSection: "triggers" | "steps" | null = null;
  let currentStep: (WorkflowIRStep & { startLine: number }) | null = null;
  let currentListProperty: "dependencies" | null = null;
  let workflowName = "Untitled Workflow";
  let workflowVersion = "draft";

  const finalizeCurrentStep = (endLine: number) => {
    if (!currentStep) {
      return;
    }

    stepLineRanges.set(currentStep.id, {
      start: currentStep.startLine,
      end: Math.max(currentStep.startLine, endLine),
    });

    steps.push({
      id: currentStep.id,
      name: currentStep.name,
      type: currentStep.type,
      dependencies: currentStep.dependencies,
      ...(currentStep.agentFqn ? { agentFqn: currentStep.agentFqn } : {}),
      ...(currentStep.reasoningMode
        ? { reasoningMode: currentStep.reasoningMode }
        : {}),
      ...(currentStep.timeout !== undefined ? { timeout: currentStep.timeout } : {}),
      ...(currentStep.retryConfig ? { retryConfig: currentStep.retryConfig } : {}),
      ...(currentStep.approvalConfig
        ? { approvalConfig: currentStep.approvalConfig }
        : {}),
    });

    currentStep = null;
    currentListProperty = null;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index] ?? "";
    const line = rawLine.replace(/\t/g, "  ");
    const indent = line.match(/^ */)?.[0].length ?? 0;
    const trimmedLine = line.trim();
    const lineNumber = index + 1;

    if (trimmedLine.length === 0 || trimmedLine.startsWith("#")) {
      continue;
    }

    if (indent === 0) {
      currentListProperty = null;

      if (trimmedLine === "triggers:") {
        finalizeCurrentStep(lineNumber - 1);
        currentSection = "triggers";
        continue;
      }

      if (trimmedLine === "steps:") {
        finalizeCurrentStep(lineNumber - 1);
        currentSection = "steps";
        continue;
      }

      if (trimmedLine.startsWith("name:")) {
        workflowName = unquote(trimmedLine.slice(5));
        continue;
      }

      if (trimmedLine.startsWith("version:")) {
        workflowVersion = unquote(trimmedLine.slice(8));
        continue;
      }
    }

    if (currentSection === "triggers" && indent === 2 && trimmedLine.startsWith("- ")) {
      const triggerValue = trimmedLine.slice(2).trim();
      if (triggerValue.startsWith("type:")) {
        triggers.push({
          type: unquote(triggerValue.slice(5)) as WorkflowTrigger["type"],
          config: {},
        });
      }
      continue;
    }

    if (currentSection !== "steps") {
      continue;
    }

    if (indent === 2 && trimmedLine.endsWith(":")) {
      finalizeCurrentStep(lineNumber - 1);

      const stepId = trimmedLine.slice(0, -1).trim();
      if (!stepId) {
        return {
          workflowIr: null,
          parseError: `Invalid step identifier on line ${lineNumber}`,
          stepLineRanges,
        };
      }

      currentStep = {
        id: stepId,
        name: toTitleCase(stepId),
        type: "agent_task",
        dependencies: [],
        startLine: lineNumber,
      };
      continue;
    }

    if (!currentStep) {
      continue;
    }

    if (currentListProperty === "dependencies" && indent >= 6 && trimmedLine.startsWith("- ")) {
      currentStep.dependencies.push(unquote(trimmedLine.slice(2)));
      continue;
    }

    currentListProperty = null;

    if (indent < 4 || !trimmedLine.includes(":")) {
      continue;
    }

    const separatorIndex = trimmedLine.indexOf(":");
    const property = trimmedLine.slice(0, separatorIndex).trim();
    const value = trimmedLine.slice(separatorIndex + 1).trim();

    switch (property) {
      case "type":
        currentStep.type = unquote(value) as WorkflowStepType;
        break;
      case "name":
        currentStep.name = unquote(value);
        break;
      case "agent_fqn":
        currentStep.agentFqn = unquote(value);
        break;
      case "reasoning_mode":
        currentStep.reasoningMode = unquote(
          value,
        ) as NonNullable<WorkflowIRStep["reasoningMode"]>;
        break;
      case "timeout":
        currentStep.timeout = Number(value);
        break;
      case "dependencies":
        if (!value) {
          currentListProperty = "dependencies";
        } else {
          currentStep.dependencies = parseInlineArray(value);
        }
        break;
      default:
        break;
    }
  }

  finalizeCurrentStep(lines.length);

  if (steps.length === 0) {
    return {
      workflowIr: null,
      parseError: "No steps found in YAML definition",
      stepLineRanges,
    };
  }

  const seenIds = new Set<string>();
  for (const step of steps) {
    if (seenIds.has(step.id)) {
      return {
        workflowIr: null,
        parseError: `Duplicate step id "${step.id}" detected`,
        stepLineRanges,
      };
    }

    seenIds.add(step.id);
  }

  for (const step of steps) {
    for (const dependency of step.dependencies) {
      if (!seenIds.has(dependency)) {
        return {
          workflowIr: null,
          parseError: `Unknown dependency "${dependency}" referenced by step "${step.id}"`,
          stepLineRanges,
        };
      }
    }
  }

  const cycleError = detectCycle(steps);
  if (cycleError) {
    return {
      workflowIr: null,
      parseError: cycleError,
      stepLineRanges,
    };
  }

  return {
    workflowIr: {
      metadata: {
        name: workflowName,
        description: null,
        version: workflowVersion || "draft",
      },
      steps,
      triggers,
    },
    parseError: null,
    stepLineRanges,
  };
}

function buildErroredStepSet(
  stepLineRanges: Map<string, StepLineRange>,
  validationErrors: ValidationError[],
): Set<string> {
  if (validationErrors.length === 0 || stepLineRanges.size === 0) {
    return new Set();
  }

  return new Set(
    Array.from(stepLineRanges.entries())
      .filter(([, range]) =>
        validationErrors.some(
          (error) => error.line >= range.start && error.line <= range.end,
        ),
      )
      .map(([stepId]) => stepId),
  );
}

function buildGraphLayout(
  workflowIr: WorkflowIR,
  erroredSteps: Set<string>,
): WorkflowGraphResult {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: "TB",
    align: "UL",
    nodesep: 36,
    ranksep: 72,
    marginx: 24,
    marginy: 24,
  });
  graph.setDefaultEdgeLabel(() => ({}));

  for (const step of workflowIr.steps) {
    graph.setNode(step.id, {
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    });
  }

  const edges: WorkflowGraphEdge[] = workflowIr.steps.flatMap((step) =>
    step.dependencies.map((dependency) => {
      graph.setEdge(dependency, step.id);
      return {
        id: `${dependency}->${step.id}`,
        source: dependency,
        target: step.id,
        type: "smoothstep" as const,
      };
    }),
  );

  dagre.layout(graph);

  const nodes: WorkflowGraphNode[] = workflowIr.steps.map((step) => {
    const node = graph.node(step.id);

    return {
      id: step.id,
      type: "step",
      position: {
        x: (node?.x ?? 0) - NODE_WIDTH / 2,
        y: (node?.y ?? 0) - NODE_HEIGHT / 2,
      },
      data: {
        stepId: step.id,
        label: step.name,
        stepType: step.type,
        ...(step.agentFqn ? { agentFqn: step.agentFqn } : {}),
        hasValidationError: erroredSteps.has(step.id),
      },
    };
  });

  return {
    nodes,
    edges,
    parseError: null,
  };
}

export function useWorkflowGraph({
  compiledIr,
  yamlContent,
  baselineYamlContent,
  validationErrors = [],
}: UseWorkflowGraphOptions): WorkflowGraphResult {
  return useMemo(() => {
    const normalizedYaml = (yamlContent ?? "").trim();
    const normalizedBaselineYaml = (baselineYamlContent ?? "").trim();
    const shouldParseYaml =
      normalizedYaml.length > 0 &&
      (!compiledIr || normalizedYaml !== normalizedBaselineYaml);

    const parsedDefinition = shouldParseYaml
      ? parseWorkflowYaml(yamlContent ?? "")
      : normalizedYaml.length > 0
        ? parseWorkflowYaml(yamlContent ?? "")
        : {
            workflowIr: compiledIr ?? null,
            parseError: null,
            stepLineRanges: new Map<string, StepLineRange>(),
          };

    const workflowIr = shouldParseYaml
      ? parsedDefinition.workflowIr
      : compiledIr ?? parsedDefinition.workflowIr;

    const parseError = shouldParseYaml ? parsedDefinition.parseError : null;
    if (!workflowIr || parseError) {
      return {
        nodes: [],
        edges: [],
        parseError,
      };
    }

    const erroredSteps = buildErroredStepSet(
      parsedDefinition.stepLineRanges,
      validationErrors,
    );

    return buildGraphLayout(workflowIr, erroredSteps);
  }, [baselineYamlContent, compiledIr, validationErrors, yamlContent]);
}
