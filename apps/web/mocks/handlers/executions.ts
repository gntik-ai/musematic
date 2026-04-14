import { http, HttpResponse } from "msw";
import type {
  ExecutionEventResponse,
  ExecutionListResponse,
  ExecutionResponse,
  ExecutionStateResponse,
  StepDetailResponse,
  StepResultResponse,
} from "@/types/execution";
import { workflowFixtures } from "@/mocks/handlers/workflows";

function buildExecution(
  id: string,
  workflowId: string,
  workflowVersionId: string,
  workflowVersionNumber: number,
  status: ExecutionResponse["status"],
  startedAt: string,
): ExecutionResponse {
  return {
    id,
    workflow_id: workflowId,
    workflow_version_id: workflowVersionId,
    workflow_version_number: workflowVersionNumber,
    status,
    triggered_by: "user-1",
    correlation_context: {
      workspace_id: "workspace-1",
      execution_id: id,
      workflow_id: workflowId,
      conversation_id: "conversation-1",
    },
    started_at: startedAt,
    completed_at:
      status === "completed" || status === "failed" || status === "canceled"
        ? new Date("2026-04-13T09:15:00.000Z").toISOString()
        : null,
    failure_reason: status === "failed" ? "Step evaluate_risk exceeded retry budget" : null,
  };
}

function buildStepResult(
  stepId: string,
  status: StepResultResponse["status"],
  retryCount = 0,
): StepResultResponse {
  return {
    step_id: stepId,
    status,
    started_at:
      status === "pending" ? null : new Date("2026-04-13T09:00:00.000Z").toISOString(),
    completed_at:
      status === "completed" || status === "failed" || status === "skipped"
        ? new Date("2026-04-13T09:05:00.000Z").toISOString()
        : null,
    duration_ms:
      status === "completed" || status === "failed" || status === "skipped"
        ? 48_000
        : null,
    error:
      status === "failed"
        ? {
            code: "RISK_TIMEOUT",
            message: "The risk evaluator timed out.",
            details: { timeout_ms: 30_000 },
          }
        : null,
    retry_count: retryCount,
  };
}

function buildState(
  executionId: string,
  status: ExecutionStateResponse["status"],
  stepStatuses: Record<string, StepResultResponse["status"]>,
): ExecutionStateResponse {
  const entries = Object.entries(stepStatuses);

  return {
    execution_id: executionId,
    status,
    completed_step_ids: entries
      .filter(([, value]) => value === "completed")
      .map(([key]) => key),
    active_step_ids: entries
      .filter(([, value]) => value === "running")
      .map(([key]) => key),
    pending_step_ids: entries
      .filter(([, value]) => value === "pending")
      .map(([key]) => key),
    failed_step_ids: entries
      .filter(([, value]) => value === "failed")
      .map(([key]) => key),
    skipped_step_ids: entries
      .filter(([, value]) => value === "skipped")
      .map(([key]) => key),
    waiting_for_approval_step_ids: entries
      .filter(([, value]) => value === "waiting_for_approval")
      .map(([key]) => key),
    step_results: Object.fromEntries(
      entries.map(([stepId, stepStatus]) => [stepId, buildStepResult(stepId, stepStatus)]),
    ),
    last_event_sequence: 4,
    updated_at: new Date("2026-04-13T09:05:00.000Z").toISOString(),
  };
}

function buildStepDetail(
  executionId: string,
  stepId: string,
  status: StepDetailResponse["status"],
): StepDetailResponse {
  return {
    execution_id: executionId,
    step_id: stepId,
    status,
    inputs: { customer_id: "cust-123", region: "EU" },
    outputs:
      status === "completed"
        ? { summary: `${stepId} completed successfully`, score: 0.92 }
        : null,
    started_at:
      status === "pending" ? null : new Date("2026-04-13T09:00:00.000Z").toISOString(),
    completed_at:
      status === "completed" || status === "failed"
        ? new Date("2026-04-13T09:05:00.000Z").toISOString()
        : null,
    duration_ms: status === "pending" ? null : 48_000,
    context_quality_score: status === "pending" ? null : 0.88,
    error:
      status === "failed"
        ? {
            code: "RISK_TIMEOUT",
            message: "The risk evaluator timed out.",
            details: { timeout_ms: 30_000 },
          }
        : null,
    token_usage:
      status === "pending"
        ? null
        : {
            input_tokens: 420,
            output_tokens: 128,
            total_tokens: 548,
            estimated_cost_usd: 0.0234,
          },
  };
}

function buildJournal(executionId: string): ExecutionEventResponse[] {
  return [
    {
      id: `${executionId}-evt-1`,
      execution_id: executionId,
      sequence: 1,
      event_type: "EXECUTION_CREATED",
      step_id: null,
      agent_fqn: null,
      payload: {},
      created_at: new Date("2026-04-13T09:00:00.000Z").toISOString(),
    },
    {
      id: `${executionId}-evt-2`,
      execution_id: executionId,
      sequence: 2,
      event_type: "STEP_COMPLETED",
      step_id: "collect_context",
      agent_fqn: "operations/context-loader",
      payload: { output: { summary: "Context loaded" } },
      created_at: new Date("2026-04-13T09:01:00.000Z").toISOString(),
    },
    {
      id: `${executionId}-evt-3`,
      execution_id: executionId,
      sequence: 3,
      event_type: "REASONING_TRACE_EMITTED",
      step_id: "evaluate_risk",
      agent_fqn: "trust/risk-evaluator",
      payload: {
        reasoning_trace: {
          execution_id: executionId,
          step_id: "evaluate_risk",
          tree_id: `${executionId}-tree-1`,
          root_branch_id: `${executionId}-branch-root`,
          total_branches: 2,
          budget_summary: {
            mode: "tree_of_thought",
            max_tokens: 4000,
            used_tokens: 820,
            max_rounds: 4,
            used_rounds: 2,
            max_cost_usd: 0.35,
            used_cost_usd: 0.06,
            status: "completed",
          },
          branches: [
            {
              id: `${executionId}-branch-root`,
              parent_id: null,
              depth: 0,
              status: "completed",
              chain_of_thought: [
                {
                  index: 1,
                  thought: "Aggregate customer signals before policy review.",
                  confidence: 0.71,
                  token_cost: 120,
                },
              ],
              token_usage: {
                input_tokens: 320,
                output_tokens: 90,
                total_tokens: 410,
                estimated_cost_usd: 0.018,
              },
              budget_remaining_at_completion: 3180,
              created_at: new Date("2026-04-13T09:02:00.000Z").toISOString(),
              completed_at: new Date("2026-04-13T09:03:00.000Z").toISOString(),
            },
            {
              id: `${executionId}-branch-alt`,
              parent_id: `${executionId}-branch-root`,
              depth: 1,
              status: "pruned",
              chain_of_thought: [
                {
                  index: 1,
                  thought: "Alternative branch pruned due to lower confidence.",
                  confidence: 0.42,
                  token_cost: 88,
                },
              ],
              token_usage: {
                input_tokens: 210,
                output_tokens: 48,
                total_tokens: 258,
                estimated_cost_usd: 0.011,
              },
              budget_remaining_at_completion: 2922,
              created_at: new Date("2026-04-13T09:02:30.000Z").toISOString(),
              completed_at: new Date("2026-04-13T09:03:20.000Z").toISOString(),
            },
          ],
        },
        self_correction_loop: {
          loop_id: `${executionId}-loop-1`,
          execution_id: executionId,
          step_id: "evaluate_risk",
          final_status: "converged",
          started_at: new Date("2026-04-13T09:02:00.000Z").toISOString(),
          completed_at: new Date("2026-04-13T09:03:30.000Z").toISOString(),
          budget_consumed: {
            tokens: 820,
            cost_usd: 0.06,
            rounds: 2,
          },
          iterations: [
            {
              iteration_number: 1,
              quality_score: 0.61,
              delta: 0.61,
              status: "continue",
              token_cost: 220,
              duration_ms: 16_000,
              thoughts: "Initial screening surfaced two ambiguous signals.",
            },
            {
              iteration_number: 2,
              quality_score: 0.88,
              delta: 0.27,
              status: "converged",
              token_cost: 180,
              duration_ms: 12_000,
              thoughts: "Second pass resolved ambiguity against trusted context.",
            },
          ],
        },
      },
      created_at: new Date("2026-04-13T09:03:00.000Z").toISOString(),
    },
    {
      id: `${executionId}-evt-4`,
      execution_id: executionId,
      sequence: 4,
      event_type: "BUDGET_THRESHOLD_80",
      step_id: "evaluate_risk",
      agent_fqn: "trust/risk-evaluator",
      payload: { step_id: "evaluate_risk", tokens: 820, cost_usd: 0.06 },
      created_at: new Date("2026-04-13T09:03:30.000Z").toISOString(),
    },
  ];
}

export interface ExecutionMockState {
  executionsByWorkflowId: Record<string, ExecutionResponse[]>;
  executionsById: Record<string, ExecutionResponse>;
  statesByExecutionId: Record<string, ExecutionStateResponse>;
  journalByExecutionId: Record<string, ExecutionEventResponse[]>;
  stepDetailsByExecutionId: Record<string, Record<string, StepDetailResponse>>;
}

export function createExecutionMockState(): ExecutionMockState {
  const workflowOne = workflowFixtures.definitions.find(
    (definition) => definition.id === "workflow-1",
  ) ?? workflowFixtures.definitions[0];
  const workflowTwo = workflowFixtures.definitions.find(
    (definition) => definition.id === "workflow-2",
  ) ?? workflowFixtures.definitions[1];

  if (!workflowOne || !workflowTwo) {
    throw new Error("Workflow fixtures must include workflow-1 and workflow-2");
  }

  const running = buildExecution(
    "execution-1",
    workflowOne.id,
    workflowOne.current_version_id,
    workflowOne.current_version_number,
    "running",
    new Date("2026-04-13T09:00:00.000Z").toISOString(),
  );
  const completed = buildExecution(
    "execution-2",
    workflowOne.id,
    workflowOne.current_version_id,
    workflowOne.current_version_number,
    "completed",
    new Date("2026-04-13T07:00:00.000Z").toISOString(),
  );
  const failed = buildExecution(
    "execution-3",
    workflowTwo.id,
    workflowTwo.current_version_id,
    workflowTwo.current_version_number,
    "failed",
    new Date("2026-04-13T06:00:00.000Z").toISOString(),
  );

  const allExecutions = [running, completed, failed];

  return {
    executionsByWorkflowId: {
      [workflowOne.id]: [running, completed],
      [workflowTwo.id]: [failed],
    },
    executionsById: Object.fromEntries(allExecutions.map((execution) => [execution.id, execution])),
    statesByExecutionId: {
      "execution-1": buildState("execution-1", "running", {
        collect_context: "completed",
        evaluate_risk: "running",
        approval_gate: "pending",
        finalize_case: "pending",
      }),
      "execution-2": buildState("execution-2", "completed", {
        collect_context: "completed",
        evaluate_risk: "completed",
        approval_gate: "completed",
        finalize_case: "completed",
      }),
      "execution-3": buildState("execution-3", "failed", {
        collect_context: "completed",
        evaluate_risk: "failed",
        approval_gate: "pending",
        finalize_case: "pending",
      }),
    },
    journalByExecutionId: {
      "execution-1": buildJournal("execution-1"),
      "execution-2": buildJournal("execution-2"),
      "execution-3": buildJournal("execution-3"),
    },
    stepDetailsByExecutionId: {
      "execution-1": {
        collect_context: buildStepDetail("execution-1", "collect_context", "completed"),
        evaluate_risk: buildStepDetail("execution-1", "evaluate_risk", "running"),
        approval_gate: buildStepDetail(
          "execution-1",
          "approval_gate",
          "waiting_for_approval",
        ),
        finalize_case: buildStepDetail("execution-1", "finalize_case", "pending"),
      },
      "execution-2": {
        collect_context: buildStepDetail("execution-2", "collect_context", "completed"),
        evaluate_risk: buildStepDetail("execution-2", "evaluate_risk", "completed"),
        approval_gate: buildStepDetail("execution-2", "approval_gate", "completed"),
        finalize_case: buildStepDetail("execution-2", "finalize_case", "completed"),
      },
      "execution-3": {
        collect_context: buildStepDetail("execution-3", "collect_context", "completed"),
        evaluate_risk: buildStepDetail("execution-3", "evaluate_risk", "failed"),
        approval_gate: buildStepDetail("execution-3", "approval_gate", "pending"),
        finalize_case: buildStepDetail("execution-3", "finalize_case", "pending"),
      },
    },
  };
}

export const executionFixtures: ExecutionMockState = createExecutionMockState();

export function resetExecutionFixtures(): void {
  const fresh = createExecutionMockState();
  executionFixtures.executionsByWorkflowId = fresh.executionsByWorkflowId;
  executionFixtures.executionsById = fresh.executionsById;
  executionFixtures.statesByExecutionId = fresh.statesByExecutionId;
  executionFixtures.journalByExecutionId = fresh.journalByExecutionId;
  executionFixtures.stepDetailsByExecutionId = fresh.stepDetailsByExecutionId;
}

function appendJournalEvent(
  executionId: string,
  eventType: ExecutionEventResponse["event_type"],
  stepId: string | null,
  payload: Record<string, unknown>,
): void {
  const events = executionFixtures.journalByExecutionId[executionId] ?? [];
  const sequence = (events.at(-1)?.sequence ?? 0) + 1;
  executionFixtures.journalByExecutionId[executionId] = [
    ...events,
    {
      id: `${executionId}-evt-${sequence}`,
      execution_id: executionId,
      sequence,
      event_type: eventType,
      step_id: stepId,
      agent_fqn: null,
      payload,
      created_at: new Date().toISOString(),
    },
  ];

  const state = executionFixtures.statesByExecutionId[executionId];
  if (state) {
    state.last_event_sequence = sequence;
    state.updated_at = new Date().toISOString();
  }
}

export const executionHandlers = [
  http.get("*/api/v1/executions", ({ request }) => {
    const url = new URL(request.url);
    const workflowId = url.searchParams.get("workflow_id") ?? "";
    const cursor = Number(url.searchParams.get("cursor") ?? "0");
    const limit = Number(url.searchParams.get("limit") ?? "20");
    const items = executionFixtures.executionsByWorkflowId[workflowId] ?? [];
    const slice = items.slice(cursor, cursor + limit);
    const response: ExecutionListResponse = {
      items: slice,
      next_cursor: cursor + slice.length < items.length ? String(cursor + slice.length) : null,
      total: items.length,
    };

    return HttpResponse.json(response);
  }),
  http.post("*/api/v1/executions", async ({ request }) => {
    const body = (await request.json()) as {
      workflow_version_id: string;
      trigger_type: "manual";
    };
    const workflow = workflowFixtures.definitions.find(
      (definition) => definition.current_version_id === body.workflow_version_id,
    );

    if (!workflow) {
      return HttpResponse.json(
        { code: "NOT_FOUND", message: "Workflow version not found", details: {} },
        { status: 404 },
      );
    }

    const nextExecutionId = `execution-${Object.keys(executionFixtures.executionsById).length + 1}`;
    const execution = buildExecution(
      nextExecutionId,
      workflow.id,
      body.workflow_version_id,
      workflow.current_version_number,
      "queued",
      new Date().toISOString(),
    );
    executionFixtures.executionsById[nextExecutionId] = execution;
    executionFixtures.executionsByWorkflowId[workflow.id] = [
      execution,
      ...(executionFixtures.executionsByWorkflowId[workflow.id] ?? []),
    ];
    executionFixtures.statesByExecutionId[nextExecutionId] = buildState(
      nextExecutionId,
      "queued",
      {
        collect_context: "pending",
        evaluate_risk: "pending",
        approval_gate: "pending",
        finalize_case: "pending",
      },
    );
    executionFixtures.journalByExecutionId[nextExecutionId] = [];
    executionFixtures.stepDetailsByExecutionId[nextExecutionId] = {
      collect_context: buildStepDetail(nextExecutionId, "collect_context", "pending"),
      evaluate_risk: buildStepDetail(nextExecutionId, "evaluate_risk", "pending"),
      approval_gate: buildStepDetail(nextExecutionId, "approval_gate", "pending"),
      finalize_case: buildStepDetail(nextExecutionId, "finalize_case", "pending"),
    };

    return HttpResponse.json(execution, { status: 201 });
  }),
  http.get("*/api/v1/executions/:executionId", ({ params }) => {
    const executionId = String(params.executionId);
    const execution = executionFixtures.executionsById[executionId];

    if (!execution) {
      return HttpResponse.json(
        { code: "NOT_FOUND", message: "Execution not found", details: {} },
        { status: 404 },
      );
    }

    return HttpResponse.json(execution);
  }),
  http.get("*/api/v1/executions/:executionId/state", ({ params }) => {
    const executionId = String(params.executionId);
    const state = executionFixtures.statesByExecutionId[executionId];

    if (!state) {
      return HttpResponse.json(
        { code: "NOT_FOUND", message: "Execution state not found", details: {} },
        { status: 404 },
      );
    }

    return HttpResponse.json(state);
  }),
  http.get("*/api/v1/executions/:executionId/journal", ({ params, request }) => {
    const executionId = String(params.executionId);
    const url = new URL(request.url);
    const sinceSequence = Number(url.searchParams.get("since_sequence") ?? "0");
    const eventType = url.searchParams.get("event_type");
    const stepId = url.searchParams.get("step_id");
    const limit = Number(url.searchParams.get("limit") ?? "50");
    const offset = Number(url.searchParams.get("offset") ?? "0");
    const events = executionFixtures.journalByExecutionId[executionId] ?? [];
    const filtered = events.filter((event) => {
      if (event.sequence < sinceSequence) {
        return false;
      }
      if (eventType && event.event_type !== eventType) {
        return false;
      }
      if (stepId && event.step_id !== stepId) {
        return false;
      }
      return true;
    });

    return HttpResponse.json({
      events: filtered.slice(offset, offset + limit),
      total: filtered.length,
    });
  }),
  http.get("*/api/v1/executions/:executionId/steps/:stepId", ({ params }) => {
    const executionId = String(params.executionId);
    const stepId = String(params.stepId);
    const detail = executionFixtures.stepDetailsByExecutionId[executionId]?.[stepId];

    if (!detail) {
      return HttpResponse.json(
        { code: "NOT_FOUND", message: "Step detail not found", details: {} },
        { status: 404 },
      );
    }

    return HttpResponse.json(detail);
  }),
  http.post("*/api/v1/executions/:executionId/pause", ({ params }) => {
    const executionId = String(params.executionId);
    const execution = executionFixtures.executionsById[executionId];
    if (execution) {
      execution.status = "paused";
    }
    const state = executionFixtures.statesByExecutionId[executionId];
    if (state) {
      state.status = "paused";
    }
    appendJournalEvent(executionId, "EXECUTION_PAUSED", null, {});
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/executions/:executionId/resume", ({ params }) => {
    const executionId = String(params.executionId);
    const execution = executionFixtures.executionsById[executionId];
    if (execution) {
      execution.status = "running";
    }
    const state = executionFixtures.statesByExecutionId[executionId];
    if (state) {
      state.status = "running";
    }
    appendJournalEvent(executionId, "EXECUTION_RESUMED", null, {});
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/executions/:executionId/cancel", ({ params }) => {
    const executionId = String(params.executionId);
    const execution = executionFixtures.executionsById[executionId];
    if (execution) {
      execution.status = "canceled";
      execution.completed_at = new Date().toISOString();
    }
    const state = executionFixtures.statesByExecutionId[executionId];
    if (state) {
      state.status = "canceled";
    }
    appendJournalEvent(executionId, "EXECUTION_CANCELED", null, {});
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/executions/:executionId/steps/:stepId/retry", ({ params }) => {
    const executionId = String(params.executionId);
    const stepId = String(params.stepId);
    const state = executionFixtures.statesByExecutionId[executionId];
    const detail = executionFixtures.stepDetailsByExecutionId[executionId]?.[stepId];
    if (state) {
      state.status = "running";
      state.failed_step_ids = state.failed_step_ids.filter((entry) => entry !== stepId);
      if (!state.active_step_ids.includes(stepId)) {
        state.active_step_ids.push(stepId);
      }
      state.step_results[stepId] = buildStepResult(stepId, "running", 1);
    }
    if (detail) {
      detail.status = "running";
      detail.error = null;
    }
    appendJournalEvent(executionId, "STEP_RETRIED", stepId, {});
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/executions/:executionId/steps/:stepId/skip", ({ params }) => {
    const executionId = String(params.executionId);
    const stepId = String(params.stepId);
    const state = executionFixtures.statesByExecutionId[executionId];
    if (state) {
      state.active_step_ids = state.active_step_ids.filter((entry) => entry !== stepId);
      if (!state.skipped_step_ids.includes(stepId)) {
        state.skipped_step_ids.push(stepId);
      }
      state.step_results[stepId] = buildStepResult(stepId, "skipped");
    }
    const detail = executionFixtures.stepDetailsByExecutionId[executionId]?.[stepId];
    if (detail) {
      detail.status = "skipped";
    }
    appendJournalEvent(executionId, "STEP_SKIPPED", stepId, {});
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/executions/:executionId/hot-change", ({ params }) => {
    const executionId = String(params.executionId);
    appendJournalEvent(executionId, "HOT_CHANGED", null, {});
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/executions/:executionId/approvals/:stepId/decide", async ({ params, request }) => {
    const executionId = String(params.executionId);
    const stepId = String(params.stepId);
    const body = (await request.json()) as { decision: "approved" | "rejected" };
    const state = executionFixtures.statesByExecutionId[executionId];

    if (state) {
      state.waiting_for_approval_step_ids = state.waiting_for_approval_step_ids.filter(
        (entry) => entry !== stepId,
      );
      state.step_results[stepId] = buildStepResult(
        stepId,
        body.decision === "approved" ? "completed" : "failed",
      );
      if (body.decision === "approved") {
        state.completed_step_ids.push(stepId);
      } else {
        state.failed_step_ids.push(stepId);
      }
    }

    appendJournalEvent(
      executionId,
      body.decision === "approved" ? "STEP_APPROVED" : "STEP_REJECTED",
      stepId,
      { decision: body.decision },
    );

    return new HttpResponse(null, { status: 204 });
  }),
];
