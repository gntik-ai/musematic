"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import type { SurveillanceSignal } from "@/types/operator";

const trustApi = createApiClient(
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
  return fallback;
}

function normalizeSignal(raw: unknown): SurveillanceSignal {
  const item = asRecord(raw);
  return {
    id: asString(item.id),
    agentId: asString(item.agent_id ?? item.agentId),
    signalType: asString(item.signal_type ?? item.signalType),
    score: asNumber(item.score_contribution ?? item.score),
    timestamp: asString(item.created_at ?? item.timestamp),
    summary: asString(item.source_type ?? item.summary, "Signal"),
  };
}

export function useSurveillanceSignals(agentId: string) {
  const query = useAppQuery<{ items: SurveillanceSignal[]; total: number }>(
    ["surveillance", agentId],
    async () => {
      const response = await trustApi.get<{ items?: unknown[]; total?: number }>(
        `/api/v1/trust/agents/${encodeURIComponent(agentId)}/signals?page=1&page_size=20`,
      );
      return {
        items: (response.items ?? []).map(normalizeSignal),
        total: response.total ?? 0,
      };
    },
    {
      enabled: Boolean(agentId),
    },
  );

  return {
    ...query,
    signals: query.data?.items ?? [],
  };
}
