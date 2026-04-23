"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import type { RubricDimension, TrajectoryComparisonMethod } from "@/types/evaluation";
import { evalQueryKeys } from "@/types/evaluation";

const evaluationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface RubricCriterionPayload {
  name?: unknown;
  description?: unknown;
  weight?: unknown;
  scale_max?: unknown;
  scale?: unknown;
}

interface EvalSetPayload {
  id: string;
  name: string;
  scorer_config?: Record<string, unknown>;
}

interface RubricPayload {
  id: string;
  name: string;
  description: string;
  criteria: RubricCriterionPayload[];
}

export interface RubricEditorRecord {
  id: string | null;
  name: string;
  description: string;
  dimensions: RubricDimension[];
  comparisonMethod: TrajectoryComparisonMethod;
}

export interface SaveRubricInput {
  name: string;
  description: string;
  dimensions: RubricDimension[];
  comparisonMethod: TrajectoryComparisonMethod;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function resolveScorerConfig(scorerConfig: Record<string, unknown>): Record<string, unknown> {
  const trajectoryJudge = asRecord(scorerConfig.trajectory_judge);
  if (trajectoryJudge.rubric_id) {
    return trajectoryJudge;
  }
  const llmJudge = asRecord(scorerConfig.llm_judge);
  if (llmJudge.rubric_id) {
    return llmJudge;
  }
  return trajectoryJudge.rubric_id ? trajectoryJudge : llmJudge;
}

function resolveRubricId(scorerConfig: Record<string, unknown>): string | null {
  const resolved = resolveScorerConfig(scorerConfig);
  const rubricId = resolved.rubric_id;
  return typeof rubricId === "string" && rubricId.trim() !== "" ? rubricId : null;
}

function resolveCalibrationRunId(scorerConfig: Record<string, unknown>): string | null {
  const resolved = resolveScorerConfig(scorerConfig);
  const calibrationRunId = resolved.calibration_run_id;
  return typeof calibrationRunId === "string" && calibrationRunId.trim() !== ""
    ? calibrationRunId
    : null;
}

function resolveComparisonMethod(scorerConfig: Record<string, unknown>): TrajectoryComparisonMethod {
  const configured = asRecord(scorerConfig.trajectory_comparison).method;
  if (
    configured === "exact_match" ||
    configured === "semantic_similarity" ||
    configured === "edit_distance" ||
    configured === "trajectory_judge"
  ) {
    return configured;
  }

  if (asRecord(scorerConfig.trajectory_judge).enabled === true) {
    return "trajectory_judge";
  }

  if (asRecord(scorerConfig.semantic_similarity).enabled === true) {
    return "semantic_similarity";
  }

  if (asRecord(scorerConfig.edit_distance).enabled === true) {
    return "edit_distance";
  }

  return "exact_match";
}

function normalizeDimensions(criteria: RubricCriterionPayload[]): RubricDimension[] {
  const total = criteria.length || 1;
  return criteria.map((criterion, index) => ({
    id: `dimension-${index + 1}`,
    name: asString(criterion.name, `Dimension ${index + 1}`),
    description: asString(criterion.description),
    weight: asNumber(criterion.weight, Number((1 / total).toFixed(2))),
    scaleType: "numeric_1_5",
    categoricalValues: null,
  }));
}

function defaultRubricRecord(suite: EvalSetPayload): RubricEditorRecord {
  return {
    id: null,
    name: `${suite.name} rubric`,
    description: "",
    dimensions: [
      {
        id: "dimension-1",
        name: "Accuracy",
        description: "Measures how well the response satisfies the expected outcome.",
        weight: 1,
        scaleType: "numeric_1_5",
        categoricalValues: null,
      },
    ],
    comparisonMethod: resolveComparisonMethod(asRecord(suite.scorer_config)),
  };
}

async function fetchEvalSet(suiteId: string): Promise<EvalSetPayload> {
  return evaluationApi.get<EvalSetPayload>(
    `/api/v1/evaluations/eval-sets/${encodeURIComponent(suiteId)}`,
  );
}

async function fetchRubricRecord(suiteId: string): Promise<RubricEditorRecord> {
  const suite = await fetchEvalSet(suiteId);
  const scorerConfig = asRecord(suite.scorer_config);
  const rubricId = resolveRubricId(scorerConfig);
  if (!rubricId) {
    return defaultRubricRecord(suite);
  }

  const rubric = await evaluationApi.get<RubricPayload>(
    `/api/v1/evaluations/rubrics/${encodeURIComponent(rubricId)}`,
  );
  return {
    id: rubric.id,
    name: rubric.name,
    description: rubric.description,
    dimensions: normalizeDimensions(Array.isArray(rubric.criteria) ? rubric.criteria : []),
    comparisonMethod: resolveComparisonMethod(scorerConfig),
  };
}

function buildScorerConfig(
  currentConfig: Record<string, unknown>,
  rubricId: string,
  calibrationRunId: string | null,
  comparisonMethod: TrajectoryComparisonMethod,
): Record<string, unknown> {
  const nextConfig = { ...currentConfig };
  nextConfig.trajectory_comparison = { method: comparisonMethod };

  if (comparisonMethod === "trajectory_judge") {
    nextConfig.trajectory_judge = {
      ...asRecord(nextConfig.trajectory_judge),
      enabled: true,
      rubric_id: rubricId,
      ...(calibrationRunId ? { calibration_run_id: calibrationRunId } : {}),
    };
    return nextConfig;
  }

  nextConfig.llm_judge = {
    ...asRecord(nextConfig.llm_judge),
    enabled: true,
    rubric_id: rubricId,
    ...(calibrationRunId ? { calibration_run_id: calibrationRunId } : {}),
  };
  return nextConfig;
}

export function useRubricEditor(suiteId: string) {
  const queryClient = useQueryClient();
  const rubricQuery = useAppQuery<RubricEditorRecord>(
    ["rubric", suiteId],
    () => fetchRubricRecord(suiteId),
    {
      enabled: Boolean(suiteId),
    },
  );

  const saveRubric = useAppMutation<RubricEditorRecord, SaveRubricInput>(
    async (payload) => {
      const suite = await fetchEvalSet(suiteId);
      const currentConfig = asRecord(suite.scorer_config);
      const currentRubricId = resolveRubricId(currentConfig);
      const calibrationRunId = resolveCalibrationRunId(currentConfig);
      const criteria = payload.dimensions.map((dimension) => ({
        name: dimension.name,
        description: dimension.description,
        weight: dimension.weight,
        scale_min: 1,
        scale_max: 5,
        examples: {},
      }));

      const rubricPayload = {
        name: payload.name,
        description: payload.description,
        criteria,
      };

      const rubric = currentRubricId
        ? await evaluationApi.patch<RubricPayload>(
            `/api/v1/evaluations/rubrics/${encodeURIComponent(currentRubricId)}`,
            rubricPayload,
          )
        : await evaluationApi.post<RubricPayload>("/api/v1/evaluations/rubrics", rubricPayload);

      await evaluationApi.patch<EvalSetPayload>(
        `/api/v1/evaluations/eval-sets/${encodeURIComponent(suiteId)}`,
        {
          scorer_config: buildScorerConfig(
            currentConfig,
            rubric.id,
            calibrationRunId,
            payload.comparisonMethod,
          ),
        },
      );

      return {
        id: rubric.id,
        name: rubric.name,
        description: rubric.description,
        dimensions: payload.dimensions,
        comparisonMethod: payload.comparisonMethod,
      };
    },
    {
      invalidateKeys: [["rubric", suiteId], evalQueryKeys.evalSet(suiteId)],
      onSuccess: async () => {
        await queryClient.invalidateQueries({ queryKey: ["calibration", suiteId] });
      },
    },
  );

  return {
    ...rubricQuery,
    rubric: rubricQuery.data,
    saveRubric,
  };
}
