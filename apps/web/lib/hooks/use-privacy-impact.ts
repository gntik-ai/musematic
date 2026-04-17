"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import { trustWorkbenchApi } from "@/lib/hooks/use-certifications";
import type {
  PrivacyConcern,
  PrivacyDataCategory,
  PrivacyImpactAnalysis,
} from "@/lib/types/trust-workbench";

interface PrivacyImpactApiResponse {
  agentId?: string;
  agent_id?: string;
  analysisTimestamp?: string;
  analysis_timestamp?: string;
  overallCompliant?: boolean;
  overall_compliant?: boolean;
  dataSources?: string[];
  data_sources?: string[];
  categories?: Array<Record<string, unknown>>;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function normalizeConcern(raw: unknown): PrivacyConcern {
  const entry =
    typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};

  return {
    description: asString(entry.description),
    severity:
      entry.severity === "low" ||
      entry.severity === "medium" ||
      entry.severity === "high"
        ? entry.severity
        : "medium",
  };
}

function normalizeCategory(raw: Record<string, unknown>): PrivacyDataCategory {
  return {
    name: asString(raw.name),
    complianceStatus:
      raw.complianceStatus === "warning" ||
      raw.complianceStatus === "violation" ||
      raw.compliance_status === "warning" ||
      raw.compliance_status === "violation"
        ? ((raw.complianceStatus ?? raw.compliance_status) as
            | "warning"
            | "violation")
        : "compliant",
    retentionDuration: (() => {
      const value = raw.retentionDuration ?? raw.retention_duration;
      return typeof value === "string" ? value : null;
    })(),
    concerns: Array.isArray(raw.concerns) ? raw.concerns.map(normalizeConcern) : [],
    recommendations: Array.isArray(raw.recommendations)
      ? raw.recommendations.filter((value): value is string => typeof value === "string")
      : [],
  };
}

export const privacyImpactQueryKeys = {
  detail: (agentId: string | null | undefined) =>
    ["privacyImpact", agentId ?? "none"] as const,
};

export function usePrivacyImpact(agentId: string | null | undefined) {
  return useAppQuery<PrivacyImpactAnalysis>(
    privacyImpactQueryKeys.detail(agentId),
    async () => {
      const response = await trustWorkbenchApi.get<PrivacyImpactApiResponse>(
        `/api/v1/trust/agents/${encodeURIComponent(agentId ?? "")}/privacy-impact`,
      );

      return {
        agentId: asString(response.agentId ?? response.agent_id, agentId ?? ""),
        analysisTimestamp: asString(
          response.analysisTimestamp ?? response.analysis_timestamp,
          new Date(0).toISOString(),
        ),
        overallCompliant: Boolean(
          response.overallCompliant ?? response.overall_compliant,
        ),
        dataSources:
          response.dataSources ?? response.data_sources ?? [],
        categories: (response.categories ?? []).map(normalizeCategory),
      };
    },
    {
      enabled: Boolean(agentId),
      staleTime: 300_000,
    },
  );
}
