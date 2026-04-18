"use client";

import { ArrowRight, ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  ComparisonType,
  SimulationComparisonReportResponse,
} from "@/types/simulation";

export interface SimulationComparisonViewProps {
  report: SimulationComparisonReportResponse;
  type: ComparisonType;
  primaryLabel?: string | undefined;
  secondaryLabel?: string | undefined;
}

function verdictClass(verdict: SimulationComparisonReportResponse["overall_verdict"]): string {
  switch (verdict) {
    case "primary_better":
      return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
    case "secondary_better":
      return "bg-sky-500/15 text-sky-700 dark:text-sky-300";
    case "inconclusive":
      return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
    case "equivalent":
    default:
      return "text-muted-foreground";
  }
}

function verdictLabel(verdict: SimulationComparisonReportResponse["overall_verdict"]): string {
  switch (verdict) {
    case "primary_better":
      return "Primary is better";
    case "secondary_better":
      return "Secondary is better";
    case "inconclusive":
      return "Inconclusive";
    case "equivalent":
    default:
      return "Equivalent";
  }
}

export function SimulationComparisonView({
  report,
  type,
  primaryLabel,
  secondaryLabel,
}: SimulationComparisonViewProps) {
  if (report.status === "pending") {
    return (
      <div className="rounded-2xl border border-border/70 bg-card/80 p-6 text-sm text-muted-foreground">
        Comparing simulations…
      </div>
    );
  }

  if (report.status === "failed") {
    return (
      <Alert variant="destructive">
        <AlertTitle>Comparison failed</AlertTitle>
        <AlertDescription>
          The backend could not compute this comparison.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row">
        <Card className="flex-1">
          <CardHeader>
            <CardTitle>Primary</CardTitle>
          </CardHeader>
          <CardContent>{primaryLabel ?? report.primary_run_id}</CardContent>
        </Card>
        <Card className="flex-1">
          <CardHeader>
            <CardTitle>
              {type === "simulation_vs_production" ? "Production baseline" : "Secondary"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {secondaryLabel ??
              report.secondary_run_id ??
              (report.production_baseline_period ? "Production baseline" : "—")}
          </CardContent>
        </Card>
      </div>

      {report.compatible === false ? (
        <Alert className="border-amber-500/30 bg-amber-500/10 text-foreground">
          <AlertTitle>Comparison has incompatibilities</AlertTitle>
          <AlertDescription>
            {report.incompatibility_reasons.map((reason) => (
              <span className="block" key={reason}>
                {reason}
              </span>
            ))}
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex items-center justify-between gap-3 rounded-2xl border border-border/70 bg-card/80 p-4">
        <Badge className={verdictClass(report.overall_verdict)} variant="secondary">
          {verdictLabel(report.overall_verdict)}
        </Badge>
        <span className="text-sm text-muted-foreground">
          {report.metric_differences.length} tracked metrics
        </span>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-border/70 bg-card/80">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-border/70 text-left">
              <th className="px-4 py-3 font-semibold">Metric</th>
              <th className="px-4 py-3 font-semibold">Primary</th>
              <th className="px-4 py-3 font-semibold">Secondary</th>
              <th className="px-4 py-3 font-semibold">Delta</th>
              <th className="px-4 py-3 font-semibold">Direction</th>
            </tr>
          </thead>
          <tbody>
            {report.metric_differences.map((metric) => {
              const positive = metric.delta !== null && metric.delta > 0;
              const negative = metric.delta !== null && metric.delta < 0;
              const DirectionIcon = positive
                ? ArrowUpRight
                : negative
                  ? ArrowDownRight
                  : ArrowRight;
              return (
                <tr className="border-b border-border/40 last:border-b-0" key={metric.metric_name}>
                  <td className="px-4 py-3">{metric.metric_name}</td>
                  <td className="px-4 py-3">{metric.primary_value ?? "—"}</td>
                  <td className="px-4 py-3">{metric.secondary_value ?? "—"}</td>
                  <td
                    className={`px-4 py-3 ${positive ? "text-green-600 dark:text-green-400" : negative ? "text-red-600 dark:text-red-400" : "text-muted-foreground"}`}
                  >
                    {metric.delta === null ? "—" : `${metric.delta > 0 ? "+" : ""}${metric.delta}`}
                  </td>
                  <td className="px-4 py-3">
                    <DirectionIcon
                      className={`h-4 w-4 ${positive ? "text-green-600 dark:text-green-400" : negative ? "text-red-600 dark:text-red-400" : "text-muted-foreground"}`}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
