import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { createHookWrapper } from "@/lib/hooks/__tests__/test-utils";
import { useReasoningTrace } from "@/lib/hooks/use-reasoning-trace";
import { server } from "@/vitest.setup";

describe("useReasoningTrace", () => {
  beforeEach(() => {
    server.resetHandlers();
  });

  it("normalizes reasoning traces and self-correction loops from journal events", async () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useReasoningTrace("execution-1", "evaluate_risk"),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.events).toHaveLength(1);
    expect(result.current.reasoningTrace).toMatchObject({
      executionId: "execution-1",
      stepId: "evaluate_risk",
      totalBranches: 2,
      budgetSummary: {
        mode: "tree_of_thought",
        usedTokens: 820,
        status: "completed",
      },
    });
    expect(result.current.reasoningTrace?.branches).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "execution-1-branch-root",
          parentId: null,
          tokenUsage: expect.objectContaining({
            totalTokens: 410,
          }),
        }),
      ]),
    );
    expect(result.current.selfCorrectionLoop).toMatchObject({
      loopId: "execution-1-loop-1",
      finalStatus: "converged",
      budgetConsumed: {
        tokens: 820,
        costUsd: 0.06,
        rounds: 2,
      },
    });
    expect(result.current.selfCorrectionLoop?.iterations).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          iterationNumber: 1,
          status: "continue",
        }),
      ]),
    );
  });

  it("supports camelCase payloads and null-ish values", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/journal", () =>
        HttpResponse.json({
          events: [
            {
              id: "camel-evt-1",
              execution_id: "execution-camel",
              sequence: 1,
              event_type: "REASONING_TRACE_EMITTED",
              step_id: "step-a",
              agent_fqn: null,
              payload: {
                reasoningTrace: {
                  executionId: "execution-camel",
                  stepId: "step-a",
                  treeId: "tree-camel",
                  rootBranchId: "branch-root",
                  totalBranches: 1,
                  budget_summary: {
                    mode: "direct",
                    max_tokens: 256,
                    used_tokens: 12,
                    max_rounds: 1,
                    used_rounds: 1,
                    max_cost_usd: 0.02,
                    used_cost_usd: 0.001,
                    status: "active",
                  },
                  branches: [
                    {
                      id: "branch-root",
                      parentId: null,
                      depth: 0,
                      status: "active",
                      chainOfThought: [
                        {
                          thought: "Use the shortest path.",
                          confidence: null,
                          tokenCost: 12,
                        },
                      ],
                      tokenUsage: {
                        inputTokens: 8,
                        outputTokens: 4,
                        totalTokens: 12,
                        estimatedCostUsd: 0.001,
                      },
                      budgetRemainingAtCompletion: null,
                      createdAt: "2026-04-13T09:00:00.000Z",
                      completedAt: null,
                    },
                  ],
                },
                selfCorrectionLoop: {
                  loopId: "loop-camel",
                  executionId: "execution-camel",
                  stepId: "step-a",
                  finalStatus: "running",
                  startedAt: "2026-04-13T09:00:00.000Z",
                  completedAt: null,
                  budget_consumed: {
                    tokens: 12,
                    cost_usd: 0.001,
                    rounds: 1,
                  },
                  iterations: [
                    {
                      iterationNumber: 1,
                      qualityScore: 0.5,
                      delta: 0.1,
                      status: "continue",
                      tokenCost: 12,
                      durationMs: 120,
                      thoughts: null,
                    },
                  ],
                },
              },
              created_at: "2026-04-13T09:00:00.000Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useReasoningTrace("execution-camel", "step-a"),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.reasoningTrace).toMatchObject({
      executionId: "execution-camel",
      stepId: "step-a",
      branches: [
        expect.objectContaining({
          parentId: null,
          completedAt: null,
          budgetRemainingAtCompletion: null,
          chainOfThought: [
            expect.objectContaining({
              confidence: null,
            }),
          ],
        }),
      ],
    });
    expect(result.current.selfCorrectionLoop).toMatchObject({
      loopId: "loop-camel",
      completedAt: null,
      iterations: [
        expect.objectContaining({
          thoughts: null,
        }),
      ],
    });
  });

  it("stays idle and exposes no trace data until execution and step ids are present", () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(() => useReasoningTrace(null, null), {
      wrapper: Wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.events).toEqual([]);
    expect(result.current.reasoningTrace).toBeNull();
    expect(result.current.selfCorrectionLoop).toBeNull();
  });

  it("skips journal events without payloads and returns null when traces are absent", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/journal", () =>
        HttpResponse.json({
          events: [
            {
              id: "noop-evt-1",
              execution_id: "execution-empty",
              sequence: 1,
              event_type: "REASONING_TRACE_EMITTED",
              step_id: "step-a",
              agent_fqn: null,
              payload: null,
              created_at: "2026-04-13T09:00:00.000Z",
            },
            {
              id: "noop-evt-2",
              execution_id: "execution-empty",
              sequence: 2,
              event_type: "REASONING_TRACE_EMITTED",
              step_id: "step-a",
              agent_fqn: null,
              payload: {},
              created_at: "2026-04-13T09:01:00.000Z",
            },
          ],
          total: 2,
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useReasoningTrace("execution-empty", "step-a"),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.events).toHaveLength(2);
    expect(result.current.reasoningTrace).toBeNull();
    expect(result.current.selfCorrectionLoop).toBeNull();
  });

  it("fills defaults when trace and correction payloads omit optional fields", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/journal", () =>
        HttpResponse.json({
          events: [
            {
              id: "default-evt-1",
              execution_id: "execution-defaults",
              sequence: 1,
              event_type: "REASONING_TRACE_EMITTED",
              step_id: "step-b",
              agent_fqn: null,
              payload: {
                reasoning_trace: {
                  execution_id: "execution-defaults",
                  step_id: "step-b",
                  tree_id: "tree-defaults",
                  root_branch_id: "branch-defaults",
                  branches: [
                    {
                      id: "branch-defaults",
                    },
                  ],
                },
                self_correction_loop: {
                  loop_id: "loop-defaults",
                  execution_id: "execution-defaults",
                  step_id: "step-b",
                  iterations: [
                    {},
                  ],
                },
              },
              created_at: "2026-04-13T09:00:00.000Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useReasoningTrace("execution-defaults", "step-b"),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.reasoningTrace).toMatchObject({
      totalBranches: 1,
      budgetSummary: {
        mode: "direct",
        status: "active",
        usedCostUsd: 0,
      },
      branches: [
        expect.objectContaining({
          chainOfThought: [],
          budgetRemainingAtCompletion: 0,
          tokenUsage: {
            inputTokens: 0,
            outputTokens: 0,
            totalTokens: 0,
            estimatedCostUsd: 0,
          },
        }),
      ],
    });
    expect(result.current.selfCorrectionLoop).toMatchObject({
      finalStatus: "running",
      budgetConsumed: {
        tokens: 0,
        costUsd: 0,
        rounds: 0,
      },
      iterations: [
        expect.objectContaining({
          iterationNumber: 1,
          qualityScore: 0,
          status: "continue",
          tokenCost: 0,
          durationMs: 0,
          thoughts: null,
        }),
      ],
    });
  });

  it("defaults missing branch and iteration collections to empty arrays", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/journal", () =>
        HttpResponse.json({
          events: [
            {
              id: "minimal-evt-1",
              execution_id: "execution-minimal",
              sequence: 1,
              event_type: "REASONING_TRACE_EMITTED",
              step_id: "step-c",
              agent_fqn: null,
              payload: {
                reasoning_trace: {
                  execution_id: "execution-minimal",
                  step_id: "step-c",
                  tree_id: "tree-minimal",
                  root_branch_id: "branch-minimal",
                },
                self_correction_loop: {
                  loop_id: "loop-minimal",
                  execution_id: "execution-minimal",
                  step_id: "step-c",
                  iterations: null,
                },
              },
              created_at: "2026-04-13T09:00:00.000Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useReasoningTrace("execution-minimal", "step-c"),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.reasoningTrace).toMatchObject({
      totalBranches: 0,
      branches: [],
    });
    expect(result.current.selfCorrectionLoop).toMatchObject({
      iterations: [],
    });
  });

  it("keeps the journal query idle when the step id is undefined", () => {
    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useReasoningTrace("execution-1", undefined),
      {
        wrapper: Wrapper,
      },
    );

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.events).toEqual([]);
    expect(result.current.reasoningTrace).toBeNull();
    expect(result.current.selfCorrectionLoop).toBeNull();
  });

  it("fills empty strings and zero token cost when optional reasoning fields are omitted", async () => {
    server.use(
      http.get("*/api/v1/executions/:executionId/journal", () =>
        HttpResponse.json({
          events: [
            {
              id: "fallback-evt-1",
              execution_id: "execution-fallback",
              sequence: 1,
              event_type: "REASONING_TRACE_EMITTED",
              step_id: "step-d",
              agent_fqn: null,
              payload: {
                reasoning_trace: {
                  execution_id: "execution-fallback",
                  step_id: "step-d",
                  tree_id: "tree-fallback",
                  root_branch_id: "branch-fallback",
                  branches: [
                    {
                      id: "branch-fallback",
                      chain_of_thought: [{}],
                    },
                  ],
                },
                self_correction_loop: {
                  loop_id: "loop-fallback",
                  iterations: [
                    {},
                  ],
                },
              },
              created_at: "2026-04-13T09:00:00.000Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    const { Wrapper } = createHookWrapper();
    const { result } = renderHook(
      () => useReasoningTrace("execution-fallback", "step-d"),
      {
        wrapper: Wrapper,
      },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.reasoningTrace?.branches[0]?.chainOfThought[0]).toMatchObject({
      thought: "",
      tokenCost: 0,
    });
    expect(result.current.selfCorrectionLoop).toMatchObject({
      executionId: "",
      stepId: "",
    });
  });
});
