import { describe, expect, it, vi, beforeEach } from "vitest";

const hookMocks = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  apiPostMock: vi.fn(),
  useAppQueryMock: vi.fn(),
  useAppInfiniteQueryMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  createApiClient: () => ({
    get: hookMocks.apiGetMock,
    post: hookMocks.apiPostMock,
  }),
}));

vi.mock("@/lib/hooks/use-api", () => ({
  useAppQuery: hookMocks.useAppQueryMock,
  useAppInfiniteQuery: hookMocks.useAppInfiniteQueryMock,
}));

vi.mock("@/lib/stores/execution-monitor-store", () => ({
  useExecutionMonitorStore: (selector: (state: {
    totalTokens: number;
    totalCostUsd: number;
    costBreakdown: never[];
    setCostBreakdown: () => void;
  }) => unknown) =>
    selector({
      totalTokens: 0,
      totalCostUsd: 0,
      costBreakdown: [],
      setCostBreakdown: () => undefined,
    }),
}));

import { useCostTracker } from "@/lib/hooks/use-cost-tracker";
import { useExecution, useExecutionList, useExecutionState } from "@/lib/hooks/use-execution-list";
import { useExecutionJournal } from "@/lib/hooks/use-execution-journal";
import { useStepDetail } from "@/lib/hooks/use-step-detail";
import { useTaskPlan } from "@/lib/hooks/use-task-plan";
import { useWorkflow } from "@/lib/hooks/use-workflow";

type QueryResult<TValue> = {
  options: { enabled?: boolean };
  queryFn: () => Promise<TValue>;
  queryKey: unknown;
};

type InfiniteQueryResult<TValue, TCursor> = {
  options: { enabled?: boolean; initialCursor?: TCursor };
  queryFn: (cursor: TCursor | undefined) => Promise<TValue>;
  queryKey: unknown;
};

describe("workflow hook disabled-query paths", () => {
  beforeEach(() => {
    hookMocks.apiGetMock.mockReset();
    hookMocks.apiPostMock.mockReset();
    hookMocks.useAppQueryMock.mockReset();
    hookMocks.useAppInfiniteQueryMock.mockReset();

    hookMocks.useAppQueryMock.mockImplementation((queryKey, queryFn, options) => ({
      queryKey,
      queryFn,
      options,
    }));
    hookMocks.useAppInfiniteQueryMock.mockImplementation(
      (queryKey, queryFn, options) => ({
        queryKey,
        queryFn,
        options,
      }),
    );
  });

  it("builds empty-id journal and execution list paths when the identifiers are missing", async () => {
    hookMocks.apiGetMock
      .mockResolvedValueOnce({
        events: [],
        total: 0,
      })
      .mockResolvedValueOnce({
        items: [],
        next_cursor: null,
      });

    const journal = useExecutionJournal(undefined) as unknown as InfiniteQueryResult<
      { items: unknown[]; nextOffset: number | null },
      number
    >;
    const executionList = useExecutionList(undefined) as unknown as InfiniteQueryResult<
      { items: unknown[]; nextCursor: string | null },
      string | null
    >;

    expect(journal.options.enabled).toBe(false);
    expect(executionList.options.enabled).toBe(false);

    await journal.queryFn(undefined);
    await executionList.queryFn(undefined);

    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(
      1,
      "/api/v1/executions//journal?limit=50&offset=0",
    );
    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/executions?workflow_id=&limit=20",
    );
  });

  it("builds empty-id detail, state, step-detail, task-plan, and analytics paths", async () => {
    hookMocks.apiGetMock
      .mockResolvedValueOnce({
        id: "",
        workflow_id: "",
        workflow_version_id: "",
        workflow_version_number: 0,
        status: "queued",
        trigger_type: "manual",
        triggered_by: "user-1",
        correlation_context: {
          workspace_id: "workspace-1",
          execution_id: "",
          workflow_id: "",
        },
        started_at: null,
        completed_at: null,
        failure_reason: null,
      })
      .mockResolvedValueOnce({
        execution_id: "",
        status: "queued",
        completed_step_ids: [],
        active_step_ids: [],
        pending_step_ids: [],
        failed_step_ids: [],
        skipped_step_ids: [],
        waiting_for_approval_step_ids: [],
        step_results: {},
        updated_at: "2026-04-13T09:00:00.000Z",
        last_event_sequence: 0,
      })
      .mockResolvedValueOnce({
        execution_id: "",
        step_id: "",
        status: "pending",
        inputs: {},
        outputs: null,
        started_at: null,
        completed_at: null,
        duration_ms: null,
        context_quality_score: null,
        error: null,
        token_usage: null,
      })
      .mockResolvedValueOnce({
        execution_id: "",
        step_id: "",
        selected_agent_fqn: "",
        selected_tool_fqn: null,
        rationale_summary: "",
        considered_agents: [],
        considered_tools: [],
        parameters: [],
        rejected_alternatives: [],
        storage_key: "task-plan/empty",
        persisted_at: "2026-04-13T09:00:00.000Z",
      })
      .mockResolvedValueOnce({
        items: [],
      });

    const execution = useExecution(undefined) as unknown as QueryResult<unknown>;
    const executionState = useExecutionState(undefined) as unknown as QueryResult<unknown>;
    const stepDetail = useStepDetail(undefined, undefined) as unknown as QueryResult<unknown>;
    const taskPlan = useTaskPlan(undefined, undefined, false) as unknown as QueryResult<unknown>;
    const costTracker = useCostTracker(undefined);
    const breakdownQuery = costTracker.breakdownQuery as unknown as QueryResult<unknown>;

    expect(execution.options.enabled).toBe(false);
    expect(executionState.options.enabled).toBe(false);
    expect(stepDetail.options.enabled).toBe(false);
    expect(taskPlan.options.enabled).toBe(false);

    await execution.queryFn();
    await executionState.queryFn();
    await stepDetail.queryFn();
    await taskPlan.queryFn();
    await breakdownQuery.queryFn();

    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(1, "/api/v1/executions/");
    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(2, "/api/v1/executions//state");
    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(3, "/api/v1/executions//steps/");
    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(4, "/api/v1/executions//task-plan/");
    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(
      5,
      "/api/v1/analytics/usage?execution_id=",
    );
  });

  it("builds the fallback workflow version path from the fetched workflow definition", async () => {
    hookMocks.apiGetMock
      .mockResolvedValueOnce({
        id: "",
        workspace_id: "workspace-1",
        name: "Workflow without explicit id",
        description: null,
        status: "draft",
        current_version_id: "workflow-version-fallback",
        latest_version_number: 1,
        created_at: "2026-04-13T09:00:00.000Z",
        updated_at: "2026-04-13T09:00:00.000Z",
      })
      .mockResolvedValueOnce({
        id: "workflow-version-fallback",
        workflow_id: "",
        version_number: 1,
        yaml_content: "steps: {}",
        compiled_ir: {
          metadata: {
            name: "Fallback Workflow",
            description: null,
            version: "draft",
          },
          steps: [],
          triggers: [],
        },
        validation_errors: [],
        created_at: "2026-04-13T09:00:00.000Z",
        created_by: "",
      });

    const workflow = useWorkflow(undefined) as unknown as QueryResult<unknown>;

    expect(workflow.options.enabled).toBe(false);

    await workflow.queryFn();

    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(1, "/api/v1/workflows/");
    expect(hookMocks.apiGetMock).toHaveBeenNthCalledWith(
      2,
      "/api/v1/workflows//versions/workflow-version-fallback",
    );
  });
});
