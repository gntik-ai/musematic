"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { CalibrationScore } from "@/types/evaluation";

const evaluationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

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

function resolveCalibrationRunId(scorerConfig: Record<string, unknown>): string | null {
  const candidates = [
    asRecord(scorerConfig.trajectory_judge),
    asRecord(scorerConfig.llm_judge),
  ];
  for (const candidate of candidates) {
    if (typeof candidate.calibration_run_id === "string" && candidate.calibration_run_id.trim() !== "") {
      return candidate.calibration_run_id;
    }
  }
  return null;
}

function normalizeCalibrationScores(raw: Record<string, unknown>): CalibrationScore[] {
  const distribution = asRecord(raw.distribution);
  const overall = asRecord(distribution.overall);
  const dimensionsRaw = Array.isArray(distribution.dimensions)
    ? (distribution.dimensions as unknown[])
    : [];

  if (dimensionsRaw.length > 0) {
    return dimensionsRaw.map((item, index) => {
      const dimension = asRecord(item);
      const stats = asRecord(dimension.distribution ?? dimension.stats);
      const kappa = asNumber(dimension.kappa, 1);
      return {
        dimensionId: asString(dimension.dimension_id ?? dimension.id, `dimension-${index + 1}`),
        dimensionName: asString(dimension.dimension_name ?? dimension.name, `Dimension ${index + 1}`),
        distribution: {
          min: asNumber(stats.min),
          q1: asNumber(stats.q1),
          median: asNumber(stats.median),
          q3: asNumber(stats.q3),
          max: asNumber(stats.max),
        },
        kappa,
        isOutlier: kappa < 0.6,
      };
    });
  }

  const histogram = asRecord(overall.histogram);
  const values = Object.entries(histogram)
    .flatMap(([bucket, count]) => Array.from({ length: asNumber(count) }, () => Number(bucket)))
    .filter((value) => Number.isFinite(value))
    .sort((left, right) => left - right);

  if (values.length === 0) {
    return [];
  }

  const first = values[0] ?? 0;
  const median = values[Math.floor(values.length / 2)] ?? first;
  const last = values.at(-1) ?? median;
  return [
    {
      dimensionId: "overall",
      dimensionName: "Overall calibration",
      distribution: {
        min: first,
        q1: values[Math.floor(values.length * 0.25)] ?? first,
        median,
        q3: values[Math.floor(values.length * 0.75)] ?? median,
        max: last,
      },
      kappa: asNumber(raw.agreement_rate, 1),
      isOutlier: asNumber(raw.agreement_rate, 1) < 0.6,
    },
  ];
}

async function fetchCalibrationScores(suiteId: string): Promise<CalibrationScore[]> {
  const suite = await evaluationApi.get<Record<string, unknown>>(
    `/api/v1/evaluations/eval-sets/${encodeURIComponent(suiteId)}`,
  );
  const calibrationRunId = resolveCalibrationRunId(asRecord(suite.scorer_config));
  if (!calibrationRunId) {
    return [];
  }

  const calibrationRun = await evaluationApi.get<Record<string, unknown>>(
    `/api/v1/evaluations/calibration-runs/${encodeURIComponent(calibrationRunId)}`,
  );
  return normalizeCalibrationScores(calibrationRun);
}

export function useCalibrationScores(suiteId: string) {
  const query = useAppQuery<CalibrationScore[]>(
    ["calibration", suiteId],
    () => fetchCalibrationScores(suiteId),
    {
      enabled: Boolean(suiteId),
    },
  );

  return {
    ...query,
    scores: query.data ?? [],
  };
}
