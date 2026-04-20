"use client";

import { useMemo } from "react";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  executionExperienceQueryKeys,
  extractReactCycles,
  fetchStructuredReasoningTrace,
} from "@/lib/hooks/use-execution-trajectory";

export function useReactCycles(executionId: string | null | undefined) {
  const traceQuery = useAppQuery(
    executionExperienceQueryKeys.reactCycles(executionId),
    async () => fetchStructuredReasoningTrace(executionId ?? ""),
    {
      enabled: Boolean(executionId),
      staleTime: Number.POSITIVE_INFINITY,
    },
  );

  const data = useMemo(
    () => (traceQuery.data ? extractReactCycles(traceQuery.data) : undefined),
    [traceQuery.data],
  );

  return {
    ...traceQuery,
    data,
    trace: traceQuery.data,
  };
}
