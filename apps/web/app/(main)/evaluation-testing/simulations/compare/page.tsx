"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { SimulationComparisonView } from "@/components/features/simulations/SimulationComparisonView";
import { useSimulationComparison } from "@/lib/hooks/use-simulation-comparison";
import { useSimulationRun } from "@/lib/hooks/use-simulation-runs";
import type { ComparisonType } from "@/types/simulation";

function isComparisonType(value: string | null): value is ComparisonType {
  return (
    value === "simulation_vs_simulation" ||
    value === "simulation_vs_production" ||
    value === "prediction_vs_actual"
  );
}

export default function SimulationComparisonPage() {
  const searchParams = useSearchParams();
  const reportId = searchParams.get("report");
  const primaryRunId = searchParams.get("primary");
  const secondaryRunId = searchParams.get("secondary");
  const requestedType = searchParams.get("type");
  const type: ComparisonType = isComparisonType(requestedType)
    ? requestedType
    : "simulation_vs_simulation";
  const comparisonQuery = useSimulationComparison(reportId);
  const primaryRunQuery = useSimulationRun(primaryRunId ?? "");
  const secondaryRunQuery = useSimulationRun(secondaryRunId ?? "");

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <Link
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          href="/evaluation-testing/simulations"
        >
          Back to Simulations
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Simulation Comparison</h1>
      </div>
      {comparisonQuery.data ? (
        <SimulationComparisonView
          primaryLabel={primaryRunQuery.data?.name}
          report={comparisonQuery.data}
          secondaryLabel={
            type === "simulation_vs_production"
              ? "Production baseline"
              : secondaryRunQuery.data?.name
          }
          type={type}
        />
      ) : (
        <div className="rounded-2xl border border-border/70 bg-card/80 p-6 text-sm text-muted-foreground">
          Loading comparison…
        </div>
      )}
    </section>
  );
}
