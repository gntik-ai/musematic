import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useWorkflowGraph } from "@/lib/hooks/use-workflow-graph";
import type { WorkflowIR } from "@/types/workflows";

const compiledIr: WorkflowIR = {
  metadata: {
    name: "Risk Workflow",
    description: null,
    version: "1.0.0",
  },
  triggers: [{ type: "manual", config: {} }],
  steps: [
    {
      id: "collect_context",
      name: "Collect Context",
      type: "agent_task",
      dependencies: [],
    },
    {
      id: "evaluate_risk",
      name: "Evaluate Risk",
      type: "approval_gate",
      dependencies: ["collect_context"],
    },
  ],
};

describe("useWorkflowGraph", () => {
  it("builds nodes and edges from compiled IR when no editable yaml is present", () => {
    const { result } = renderHook(() =>
      useWorkflowGraph({
        compiledIr,
        yamlContent: "",
      }),
    );

    expect(result.current.parseError).toBeNull();
    expect(result.current.nodes).toHaveLength(2);
    expect(result.current.edges).toEqual([
      expect.objectContaining({
        id: "collect_context->evaluate_risk",
      }),
    ]);
  });

  it("parses yaml dependencies and flags nodes with validation errors", () => {
    const yamlContent = `
name: Risk Workflow
version: 1.0.0
steps:
  collect_context:
    type: agent_task
    name: Collect Context
  evaluate_risk:
    type: agent_task
    name: Evaluate Risk
    agent_fqn: trust/risk-evaluator
    dependencies: [collect_context]
`.trim();

    const { result } = renderHook(() =>
      useWorkflowGraph({
        yamlContent,
        validationErrors: [
          {
            line: 9,
            column: 5,
            message: "Agent is deprecated",
            severity: "warning",
            path: "steps.evaluate_risk.agent_fqn",
          },
        ],
      }),
    );

    expect(result.current.parseError).toBeNull();
    expect(result.current.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "evaluate_risk",
          data: expect.objectContaining({
            agentFqn: "trust/risk-evaluator",
            hasValidationError: true,
          }),
        }),
      ]),
    );
    expect(result.current.edges).toEqual([
      expect.objectContaining({
        source: "collect_context",
        target: "evaluate_risk",
      }),
    ]);
  });

  it("returns parse errors for invalid dependency graphs", () => {
    const missingDependency = `
name: Broken Workflow
steps:
  only_step:
    type: agent_task
    name: Only Step
    dependencies: [unknown_step]
`.trim();
    const cyclicWorkflow = `
name: Cyclic Workflow
steps:
  first:
    type: agent_task
    name: First
    dependencies: [second]
  second:
    type: agent_task
    name: Second
    dependencies: [first]
`.trim();

    const missing = renderHook(() =>
      useWorkflowGraph({
        yamlContent: missingDependency,
      }),
    );
    const cyclic = renderHook(() =>
      useWorkflowGraph({
        yamlContent: cyclicWorkflow,
      }),
    );

    expect(missing.result.current).toMatchObject({
      nodes: [],
      edges: [],
      parseError:
        'Unknown dependency "unknown_step" referenced by step "only_step"',
    });
    expect(cyclic.result.current.parseError).toBe(
      "Circular dependency detected: first -> second -> first",
    );
  });

  it("prefers the compiled IR when the editor content matches the saved baseline", () => {
    const invalidYaml = `
name: Saved Workflow
steps:
  bad_step:
    type:
`.trim();

    const { result } = renderHook(() =>
      useWorkflowGraph({
        compiledIr,
        yamlContent: invalidYaml,
        baselineYamlContent: invalidYaml,
      }),
    );

    expect(result.current.parseError).toBeNull();
    expect(result.current.nodes).toHaveLength(2);
    expect(result.current.edges).toHaveLength(1);
  });

  it("parses triggers, multiline dependency lists, reasoning modes, and timeout metadata", () => {
    const yamlContent = `
name: Escalation Flow
version: 2.0.0
triggers:
  - type: webhook
steps:
  collect_context:
    type: agent_task
    timeout: 30
  review_case:
    type: agent_task
    reasoning_mode: self_correction
    dependencies:
      - collect_context
`.trim();

    const { result } = renderHook(() =>
      useWorkflowGraph({
        yamlContent,
      }),
    );

    expect(result.current.parseError).toBeNull();
    expect(result.current.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "review_case",
          data: expect.objectContaining({
            label: "Review Case",
          }),
        }),
      ]),
    );
    expect(result.current.edges).toEqual([
      expect.objectContaining({
        source: "collect_context",
        target: "review_case",
      }),
    ]);
  });

  it("returns parse errors for empty definitions, duplicate ids, and invalid identifiers", () => {
    const emptyDefinition = renderHook(() =>
      useWorkflowGraph({
        yamlContent: "name: Missing Steps\nversion: 1.0.0",
      }),
    );
    const duplicateSteps = renderHook(() =>
      useWorkflowGraph({
        yamlContent: `
name: Duplicate Workflow
steps:
  review:
    type: agent_task
  review:
    type: approval_gate
`.trim(),
      }),
    );
    const invalidIdentifier = renderHook(() =>
      useWorkflowGraph({
        yamlContent: `
name: Invalid Identifier
steps:
  :
    type: agent_task
`.trim(),
      }),
    );

    expect(emptyDefinition.result.current.parseError).toBe(
      "No steps found in YAML definition",
    );
    expect(duplicateSteps.result.current.parseError).toBe(
      'Duplicate step id "review" detected',
    );
    expect(invalidIdentifier.result.current.parseError).toBe(
      "Invalid step identifier on line 3",
    );
  });

  it("supports scalar dependency syntax and ignores unrelated step properties", () => {
    const yamlContent = `
name: Scalar Dependency
steps:
  collect_context:
    type: agent_task
    unsupported: value
  finalize_case:
    type: agent_task
    dependencies: collect_context
`.trim();

    const { result } = renderHook(() =>
      useWorkflowGraph({
        yamlContent,
      }),
    );

    expect(result.current.parseError).toBeNull();
    expect(result.current.edges).toEqual([
      expect.objectContaining({
        source: "collect_context",
        target: "finalize_case",
      }),
    ]);
  });

  it("ignores stray yaml lines, quoted values, and empty dependency arrays", () => {
    const yamlContent = `
name: "Quoted Workflow"
steps:
  stray
  review_case:
    name: "Quoted Review"
    dependencies: []
    unexpected_line
`.trim();

    const { result } = renderHook(() =>
      useWorkflowGraph({
        yamlContent,
      }),
    );

    expect(result.current.parseError).toBeNull();
    expect(result.current.nodes).toEqual([
      expect.objectContaining({
        id: "review_case",
        data: expect.objectContaining({
          label: "Quoted Review",
        }),
      }),
    ]);
    expect(result.current.edges).toEqual([]);
  });

  it("returns an empty graph when neither compiled data nor yaml content are available", () => {
    const { result } = renderHook(() =>
      useWorkflowGraph({
        compiledIr: null,
        yamlContent: "   ",
      }),
    );

    expect(result.current).toEqual({
      nodes: [],
      edges: [],
      parseError: null,
    });
  });

  it("ignores comments and unsupported top-level sections before the steps block", () => {
    const yamlContent = `
# Comment before metadata
name: Metadata Heavy Workflow
owners:
  - platform
triggers:
  - cron
steps:
  collect_context:
    type: agent_task
`.trim();

    const { result } = renderHook(() =>
      useWorkflowGraph({
        yamlContent,
      }),
    );

    expect(result.current.parseError).toBeNull();
    expect(result.current.nodes).toEqual([
      expect.objectContaining({
        id: "collect_context",
      }),
    ]);
  });
});
