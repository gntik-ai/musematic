"use client";

import { ApiError } from "@/types/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { trustWorkbenchApi } from "@/lib/hooks/use-certifications";
import type {
  TrustDimension,
  TrustDimensionComponent,
  TrustDimensionScore,
  TrustRadarProfile,
  TrustTierName,
} from "@/lib/types/trust-workbench";
import { TRUST_DIMENSION_LABELS } from "@/lib/types/trust-workbench";

interface TrustProfileApiResponse {
  agentId?: string;
  agent_id?: string;
  agentFqn?: string;
  agent_fqn?: string;
  tier?: TrustTierName;
  overallScore?: number;
  overall_score?: number;
  dimensions?: Array<Record<string, unknown>>;
  lastComputedAt?: string;
  last_computed_at?: string;
}

interface TrustTierFallbackResponse {
  agentId?: string;
  agent_id?: string;
  agentFqn?: string;
  agent_fqn?: string;
  tier?: TrustTierName;
  certification_component?: number;
  behavioral_component?: number;
  guardrail_component?: number;
  updated_at?: string;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeDimension(
  raw: Record<string, unknown>,
): TrustDimensionScore | null {
  const dimension = raw.dimension as TrustDimension | undefined;
  if (!dimension || !(dimension in TRUST_DIMENSION_LABELS)) {
    return null;
  }

  const score = asNumber(raw.score);
  const components = Array.isArray(raw.components)
    ? raw.components.map((component) => {
        const item =
          typeof component === "object" && component !== null
            ? (component as Record<string, unknown>)
            : {};
        const trend: TrustDimensionComponent["trend"] =
          item.trend === "up" || item.trend === "down" || item.trend === "stable"
            ? (item.trend as TrustDimensionComponent["trend"])
            : undefined;

        return {
          name: asString(item.name, "Component"),
          score: asNumber(item.score),
          anomalyCount:
            typeof item.anomalyCount === "number"
              ? item.anomalyCount
              : typeof item.anomaly_count === "number"
                ? (item.anomaly_count as number)
                : undefined,
          trend,
        };
      })
    : [];

  return {
    dimension,
    label: TRUST_DIMENSION_LABELS[dimension],
    score,
    components,
    isWeak: score < 30,
  };
}

function fillMissingDimensions(
  dimensions: TrustDimensionScore[],
): TrustDimensionScore[] {
  const byDimension = new Map(dimensions.map((dimension) => [dimension.dimension, dimension]));

  return (Object.keys(TRUST_DIMENSION_LABELS) as TrustDimension[]).map((dimension) => {
    const existing = byDimension.get(dimension);
    if (existing) {
      return existing;
    }

    return {
      dimension,
      label: TRUST_DIMENSION_LABELS[dimension],
      score: 0,
      components: [{ name: "No data", score: 0, trend: "stable" }],
      isWeak: true,
    };
  });
}

function normalizeTrustProfile(raw: TrustProfileApiResponse): TrustRadarProfile {
  const dimensions = fillMissingDimensions(
    (raw.dimensions ?? [])
      .map((item) =>
        typeof item === "object" && item !== null
          ? normalizeDimension(item as Record<string, unknown>)
          : null,
      )
      .filter((item): item is TrustDimensionScore => item !== null),
  );

  return {
    agentId: asString(raw.agentId ?? raw.agent_id),
    agentFqn: asString(raw.agentFqn ?? raw.agent_fqn),
    tier: (raw.tier ?? "provisional") as TrustTierName,
    overallScore: asNumber(raw.overallScore ?? raw.overall_score),
    dimensions,
    lastComputedAt: asString(
      raw.lastComputedAt ?? raw.last_computed_at,
      new Date(0).toISOString(),
    ),
  };
}

function normalizeFallbackProfile(
  raw: TrustTierFallbackResponse,
  agentId: string,
): TrustRadarProfile {
  const certificationComponent = asNumber(raw.certification_component);
  const behavioralComponent = asNumber(raw.behavioral_component);
  const guardrailComponent = asNumber(raw.guardrail_component);

  const dimensions = fillMissingDimensions([
    {
      dimension: "certification_audit",
      label: TRUST_DIMENSION_LABELS.certification_audit,
      score: certificationComponent,
      components: [{ name: "Certification component", score: certificationComponent }],
      isWeak: certificationComponent < 30,
    },
    {
      dimension: "behavioral_compliance",
      label: TRUST_DIMENSION_LABELS.behavioral_compliance,
      score: behavioralComponent,
      components: [{ name: "Behavioral component", score: behavioralComponent }],
      isWeak: behavioralComponent < 30,
    },
    {
      dimension: "authorization_access",
      label: TRUST_DIMENSION_LABELS.authorization_access,
      score: guardrailComponent,
      components: [{ name: "Guardrail component", score: guardrailComponent }],
      isWeak: guardrailComponent < 30,
    },
  ]);

  return {
    agentId: asString(raw.agentId ?? raw.agent_id, agentId),
    agentFqn: asString(raw.agentFqn ?? raw.agent_fqn, agentId),
    tier: (raw.tier ?? "provisional") as TrustTierName,
    overallScore: Math.round(
      (certificationComponent + behavioralComponent + guardrailComponent) / 3,
    ),
    dimensions,
    lastComputedAt: asString(raw.updated_at, new Date(0).toISOString()),
  };
}

export const trustRadarQueryKeys = {
  detail: (agentId: string | null | undefined) =>
    ["trustRadar", agentId ?? "none"] as const,
};

export function useTrustRadar(agentId: string | null | undefined) {
  return useAppQuery<TrustRadarProfile>(
    trustRadarQueryKeys.detail(agentId),
    async () => {
      try {
        const response = await trustWorkbenchApi.get<TrustProfileApiResponse>(
          `/api/v1/trust/agents/${encodeURIComponent(agentId ?? "")}/trust-profile`,
        );

        return normalizeTrustProfile(response);
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) {
          const fallback = await trustWorkbenchApi.get<TrustTierFallbackResponse>(
            `/api/v1/trust/agents/${encodeURIComponent(agentId ?? "")}/tier`,
          );

          return normalizeFallbackProfile(fallback, agentId ?? "");
        }

        throw error;
      }
    },
    {
      enabled: Boolean(agentId),
    },
  );
}
