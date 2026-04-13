import { http, HttpResponse } from "msw";

export interface AnalyticsUsageItem {
  step_id: string;
  step_name: string;
  agent_fqn: string;
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface AnalyticsMockState {
  usageByExecutionId: Record<string, { items: AnalyticsUsageItem[] }>;
}

export function createAnalyticsMockState(): AnalyticsMockState {
  return {
    usageByExecutionId: {
      "execution-1": {
        items: [
          {
            step_id: "collect_context",
            step_name: "Collect Context",
            agent_fqn: "operations/context-loader",
            model_id: "gpt-5-mini",
            input_tokens: 120,
            output_tokens: 40,
            total_tokens: 160,
            cost_usd: 0.008,
          },
          {
            step_id: "evaluate_risk",
            step_name: "Evaluate Risk",
            agent_fqn: "trust/risk-evaluator",
            model_id: "gpt-5.4",
            input_tokens: 420,
            output_tokens: 128,
            total_tokens: 548,
            cost_usd: 0.0234,
          },
        ],
      },
      "execution-2": {
        items: [
          {
            step_id: "collect_context",
            step_name: "Collect Context",
            agent_fqn: "operations/context-loader",
            model_id: "gpt-5-mini",
            input_tokens: 100,
            output_tokens: 32,
            total_tokens: 132,
            cost_usd: 0.0062,
          },
        ],
      },
    },
  };
}

export const analyticsFixtures: AnalyticsMockState = createAnalyticsMockState();

export function resetAnalyticsFixtures(): void {
  const fresh = createAnalyticsMockState();
  analyticsFixtures.usageByExecutionId = fresh.usageByExecutionId;
}

export const analyticsHandlers = [
  http.get("*/api/v1/analytics/usage", ({ request }) => {
    const executionId = new URL(request.url).searchParams.get("execution_id") ?? "";
    return HttpResponse.json(
      analyticsFixtures.usageByExecutionId[executionId] ?? { items: [] },
    );
  }),
];
