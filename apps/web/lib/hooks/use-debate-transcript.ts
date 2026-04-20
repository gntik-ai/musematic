"use client";

import { useMemo } from "react";
import { useAppQuery } from "@/lib/hooks/use-api";
import {
  executionExperienceQueryKeys,
  extractDebateTurns,
  fetchStructuredReasoningTrace,
} from "@/lib/hooks/use-execution-trajectory";

export function useDebateTranscript(executionId: string | null | undefined) {
  const traceQuery = useAppQuery(
    executionExperienceQueryKeys.debate(executionId),
    async () => fetchStructuredReasoningTrace(executionId ?? ""),
    {
      enabled: Boolean(executionId),
      staleTime: Number.POSITIVE_INFINITY,
    },
  );

  const data = useMemo(
    () => (traceQuery.data ? extractDebateTurns(traceQuery.data) : undefined),
    [traceQuery.data],
  );

  return {
    ...traceQuery,
    data,
    trace: traceQuery.data,
  };
}
