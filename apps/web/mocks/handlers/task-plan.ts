import { http, HttpResponse } from "msw";
import type { TaskPlanFullResponse } from "@/types/task-plan";

function buildTaskPlan(
  executionId: string,
  stepId: string,
): TaskPlanFullResponse {
  return {
    execution_id: executionId,
    step_id: stepId,
    selected_agent_fqn: "trust/risk-evaluator",
    selected_tool_fqn: null,
    rationale_summary:
      "Selected the certified evaluator because it matched policy and latency constraints best.",
    considered_agents: [
      {
        fqn: "trust/risk-evaluator",
        display_name: "Risk Evaluator",
        suitability_score: 0.96,
        is_selected: true,
        tags: ["compliance", "latency-sensitive"],
      },
      {
        fqn: "analytics/risk-summary",
        display_name: "Risk Summary",
        suitability_score: 0.82,
        is_selected: false,
        tags: ["analysis"],
      },
    ],
    considered_tools: [],
    parameters: [
      {
        parameter_name: "customer_id",
        value: "cust-123",
        source: "execution_context",
        source_description: "From execution correlation context",
      },
      {
        parameter_name: "risk_threshold",
        value: 0.72,
        source: "workflow_definition",
        source_description: "Default in workflow definition",
      },
    ],
    rejected_alternatives: [
      {
        fqn: "analytics/risk-summary",
        rejection_reason: "Lower suitability due to missing certification badge.",
      },
    ],
    storage_key: `${executionId}/${stepId}/task-plan.json`,
    persisted_at: new Date("2026-04-13T09:03:00.000Z").toISOString(),
  };
}

export interface TaskPlanMockState {
  plansByExecutionStep: Record<string, TaskPlanFullResponse>;
}

export function createTaskPlanMockState(): TaskPlanMockState {
  return {
    plansByExecutionStep: {
      "execution-1:evaluate_risk": buildTaskPlan("execution-1", "evaluate_risk"),
      "execution-2:evaluate_risk": buildTaskPlan("execution-2", "evaluate_risk"),
    },
  };
}

export const taskPlanFixtures: TaskPlanMockState = createTaskPlanMockState();

export function resetTaskPlanFixtures(): void {
  const fresh = createTaskPlanMockState();
  taskPlanFixtures.plansByExecutionStep = fresh.plansByExecutionStep;
}

export const taskPlanHandlers = [
  http.get("*/api/v1/executions/:executionId/task-plan/:stepId", ({ params }) => {
    const executionId = String(params.executionId);
    const stepId = String(params.stepId);
    const payload = taskPlanFixtures.plansByExecutionStep[`${executionId}:${stepId}`];

    if (!payload) {
      return HttpResponse.json(
        { code: "NOT_FOUND", message: "Task plan not found", details: {} },
        { status: 404 },
      );
    }

    return HttpResponse.json(payload);
  }),
];
