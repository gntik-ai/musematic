"use client";

import { useAppQuery } from "@/lib/hooks/use-api";
import { simQueryKeys, type DigitalTwinDivergenceReport } from "@/types/simulation";
import { useSimulationRun } from "@/lib/hooks/use-simulation-runs";
import { useSimulationComparison } from "@/lib/hooks/use-simulation-comparison";

export function useDigitalTwin(runId: string, reportId?: string | null) {
  const runQuery = useSimulationRun(runId);
  const comparisonQuery = useSimulationComparison(reportId ?? "");

  return useAppQuery<DigitalTwinDivergenceReport>(
    simQueryKeys.digitalTwinReport(runId),
    async () => {
      const run = runQuery.data;
      const comparison = comparisonQuery.data;
      const fidelity = run?.scenario_config?.twin_fidelity as Record<string, unknown> | undefined;
      const mockComponents = Object.entries(fidelity ?? {})
        .filter(([, value]) => String(value).includes("mock"))
        .map(([key]) => key);
      const realComponents = Object.entries(fidelity ?? {})
        .filter(([, value]) => String(value).includes("real"))
        .map(([key]) => key);
      return {
        run_id: runId,
        mock_components: mockComponents,
        real_components: realComponents,
        divergence_points:
          comparison?.metric_differences.map((item) => ({ ...item })) ?? [],
        simulated_time_ms: Number(run?.results?.simulated_time_ms ?? 0) || null,
        wall_clock_time_ms: null,
        reference_execution_id:
          typeof comparison?.production_baseline_period?.reference_execution_id === "string"
            ? comparison.production_baseline_period.reference_execution_id
            : null,
        reference_available: Boolean(
          comparison?.production_baseline_period?.reference_execution_id,
        ),
      };
    },
    {
      enabled: Boolean(runId && runQuery.data && (!reportId || comparisonQuery.data)),
    },
  );
}
