"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { agentManagementQueryKeys } from "@/lib/hooks/use-agents";
import type {
  AgentBlueprintResponse,
  AgentDetail,
  CompositionValidationCheckResponse,
  CompositionValidationResponse,
  CreateAgentFromBlueprintRequest,
  CompositionBlueprint,
  ValidationCheck,
  ValidationResult,
} from "@/lib/types/agent-management";

const compositionApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function joinMessages(parts: string[]): string {
  return parts.filter(Boolean).join(" ").trim();
}

function normalizeBlueprint(payload: AgentBlueprintResponse): CompositionBlueprint {
  return {
    blueprint_id: payload.blueprint_id,
    description: payload.description,
    low_confidence: payload.low_confidence,
    follow_up_questions: payload.follow_up_questions
      .map((item) => String(item.question ?? "").trim())
      .filter(Boolean),
    model_config: {
      value: payload.model_config,
      reasoning: payload.llm_reasoning_summary || payload.maturity_reasoning,
      confidence: payload.confidence_score,
    },
    tool_selections: {
      value: payload.tool_selections
        .map((item) => String(item.tool_name ?? "").trim())
        .filter(Boolean),
      reasoning: payload.tool_selections
        .map((item) => String(item.relevance_justification ?? "").trim())
        .filter(Boolean)
        .join("\n"),
      confidence: payload.confidence_score,
    },
    connector_suggestions: {
      value: payload.connector_suggestions
        .map((item) => String(item.connector_name ?? "").trim())
        .filter(Boolean),
      reasoning: payload.connector_suggestions
        .map((item) => String(item.purpose ?? "").trim())
        .filter(Boolean)
        .join("\n"),
      confidence: payload.confidence_score,
    },
    policy_recommendations: {
      value: payload.policy_recommendations
        .map((item) => String(item.policy_name ?? "").trim())
        .filter(Boolean),
      reasoning: payload.policy_recommendations
        .map((item) => String(item.attachment_reason ?? "").trim())
        .filter(Boolean)
        .join("\n"),
      confidence: payload.confidence_score,
    },
    context_profile: {
      value: payload.context_profile,
      reasoning: payload.llm_reasoning_summary || payload.maturity_reasoning,
      confidence: payload.confidence_score,
    },
  };
}

function normalizeValidationCheck(
  name: string,
  check: CompositionValidationCheckResponse,
): ValidationCheck {
  const details = Array.isArray(check.details)
    ? check.details.map((item) => JSON.stringify(item)).join(" ")
    : JSON.stringify(check.details);

  return {
    name,
    passed: check.passed === true,
    message: joinMessages([
      check.status !== "ok" ? check.status : "",
      check.remediation ?? "",
      details === "{}" ? "" : details,
    ]) || null,
  };
}

function normalizeValidationResult(
  payload: CompositionValidationResponse,
): ValidationResult {
  const checks = [
    normalizeValidationCheck("Tools", payload.tools_check),
    normalizeValidationCheck("Model", payload.model_check),
    normalizeValidationCheck("Connectors", payload.connectors_check),
    normalizeValidationCheck("Policies", payload.policy_check),
  ];

  if (payload.cycle_check) {
    checks.push(normalizeValidationCheck("Cycles", payload.cycle_check));
  }

  return {
    passed: payload.overall_valid,
    checks,
  };
}

export function useGenerateBlueprint() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      description,
      workspace_id,
    }: {
      description: string;
      workspace_id: string;
    }) =>
      compositionApi
        .post<AgentBlueprintResponse>(
          "/api/v1/compositions/agent-blueprint",
        {
          description,
          workspace_id,
        },
        )
        .then(normalizeBlueprint),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({
        queryKey: agentManagementQueryKeys.blueprint(variables.workspace_id),
      });
    },
  });
}

export function useValidateBlueprint() {
  return useMutation({
    mutationFn: ({
      blueprintId,
      workspace_id,
    }: {
      blueprintId: string;
      workspace_id: string;
    }) =>
      compositionApi
        .post<CompositionValidationResponse>(
          `/api/v1/compositions/agent-blueprints/${encodeURIComponent(blueprintId)}/validate?workspace_id=${encodeURIComponent(workspace_id)}`,
        )
        .then(normalizeValidationResult),
  });
}

export function useCreateFromBlueprint() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateAgentFromBlueprintRequest) =>
      compositionApi.post<AgentDetail>("/api/v1/registry/agents", payload),
    onSuccess: async (_data, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["agent-management", "catalog"] }),
        queryClient.invalidateQueries({
          queryKey: agentManagementQueryKeys.blueprint(variables.workspace_id),
        }),
      ]);
    },
  });
}
