"use client";

import { useMemo } from "react";
import { ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAbExperiment } from "@/lib/hooks/use-ab-experiment";
import { useEvalRunVerdicts } from "@/lib/hooks/use-eval-verdicts";
import type { JudgeVerdictResponse, PairedVerdict } from "@/types/evaluation";

export interface EvalComparisonViewProps {
  experimentId: string;
  runAId: string;
  runBId: string;
}

function averageScore(verdicts: JudgeVerdictResponse[]): number | null {
  const scored = verdicts.filter((item) => typeof item.overall_score === "number");
  if (scored.length === 0) {
    return null;
  }
  return (
    scored.reduce((sum, item) => sum + (item.overall_score ?? 0), 0) / scored.length
  );
}

function passRate(verdicts: JudgeVerdictResponse[]): number | null {
  if (verdicts.length === 0) {
    return null;
  }
  const passedCount = verdicts.filter((item) => item.passed === true).length;
  return passedCount / verdicts.length;
}

function formatPercent(value: number | null): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

function buildPairedVerdicts(
  verdictsA: JudgeVerdictResponse[],
  verdictsB: JudgeVerdictResponse[],
): PairedVerdict[] {
  const verdictsAMap = new Map(
    verdictsA.map((item) => [item.benchmark_case_id, item] as const),
  );
  const verdictsBMap = new Map(
    verdictsB.map((item) => [item.benchmark_case_id, item] as const),
  );

  return Array.from(new Set([...verdictsAMap.keys(), ...verdictsBMap.keys()])).map(
    (caseId) => {
      const verdictA = verdictsAMap.get(caseId);
      const verdictB = verdictsBMap.get(caseId);
      return {
        caseId,
        caseName: caseId,
        scoreA: verdictA?.overall_score ?? null,
        scoreB: verdictB?.overall_score ?? null,
        passedA: verdictA?.passed ?? null,
        passedB: verdictB?.passed ?? null,
        delta:
          typeof verdictA?.overall_score === "number" &&
          typeof verdictB?.overall_score === "number"
            ? verdictB.overall_score - verdictA.overall_score
            : null,
      };
    },
  );
}

export function EvalComparisonView({
  experimentId,
  runAId,
  runBId,
}: EvalComparisonViewProps) {
  const experimentQuery = useAbExperiment(experimentId);
  const runAVerdictsQuery = useEvalRunVerdicts(runAId);
  const runBVerdictsQuery = useEvalRunVerdicts(runBId);

  const runAVerdicts = runAVerdictsQuery.data?.items ?? [];
  const runBVerdicts = runBVerdictsQuery.data?.items ?? [];
  const pairedVerdicts = useMemo(
    () => buildPairedVerdicts(runAVerdicts, runBVerdicts),
    [runAVerdicts, runBVerdicts],
  );
  const uniqueToRunA = pairedVerdicts.filter(
    (item) => item.scoreA !== null && item.scoreB === null,
  );
  const uniqueToRunB = pairedVerdicts.filter(
    (item) => item.scoreA === null && item.scoreB !== null,
  );

  if (!experimentId) {
    return (
      <EmptyState
        description="Select two evaluation runs before opening the comparison view."
        title="No comparison selected"
      />
    );
  }

  if (experimentQuery.isLoading || experimentQuery.data?.status === "pending") {
    return (
      <div className="rounded-2xl border border-border/70 bg-card/80 p-6 text-sm text-muted-foreground">
        Comparing runs…
      </div>
    );
  }

  if (experimentQuery.data?.status === "failed") {
    return (
      <Alert variant="destructive">
        <AlertTitle>Comparison failed</AlertTitle>
        <AlertDescription>
          {experimentQuery.data.analysis_summary ?? "The backend could not compare these runs."}
        </AlertDescription>
      </Alert>
    );
  }

  const scoreA = averageScore(runAVerdicts);
  const scoreB = averageScore(runBVerdicts);
  const passRateA = passRate(runAVerdicts);
  const passRateB = passRate(runBVerdicts);
  const winner = experimentQuery.data?.winner ?? "equivalent";

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row">
        <Card className="flex-1">
          <CardHeader>
            <CardTitle>Average score</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-2xl font-semibold">{formatPercent(scoreA)}</span>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-semibold">{formatPercent(scoreB)}</span>
            </div>
            <p className="text-muted-foreground">
              Delta:{" "}
              {typeof scoreA === "number" && typeof scoreB === "number"
                ? `${Math.round((scoreB - scoreA) * 100)} pts`
                : "—"}
            </p>
          </CardContent>
        </Card>
        <Card className="flex-1">
          <CardHeader>
            <CardTitle>Pass rate</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-2xl font-semibold">{formatPercent(passRateA)}</span>
              <ArrowRight className="h-4 w-4 text-muted-foreground" />
              <span className="text-2xl font-semibold">{formatPercent(passRateB)}</span>
            </div>
            <p className="text-muted-foreground">
              p-value {experimentQuery.data?.p_value?.toFixed(3) ?? "—"} • effect size{" "}
              {experimentQuery.data?.effect_size?.toFixed(2) ?? "—"}
            </p>
          </CardContent>
        </Card>
        <Card className="flex-1">
          <CardHeader>
            <CardTitle>Verdict</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Badge
              className={
                winner === "run_a"
                  ? "bg-sky-500/15 text-sky-700 dark:text-sky-300"
                  : winner === "run_b"
                    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                    : "text-muted-foreground"
              }
              variant="secondary"
            >
              {winner === "run_a"
                ? "Run A is better"
                : winner === "run_b"
                  ? "Run B is better"
                  : "Equivalent"}
            </Badge>
            <p className="text-sm text-muted-foreground">
              {experimentQuery.data?.analysis_summary ?? "No summary available."}
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="overflow-x-auto">
        <DataTable
          columns={[
            { accessorKey: "caseName", header: "Case" },
            {
              id: "scoreA",
              header: "Score A",
              cell: ({ row }) => formatPercent(row.original.scoreA),
            },
            {
              id: "scoreB",
              header: "Score B",
              cell: ({ row }) => formatPercent(row.original.scoreB),
            },
            {
              id: "delta",
              header: "Delta",
              cell: ({ row }) => {
                if (row.original.delta === null) {
                  return "—";
                }

                const positive = row.original.delta > 0;
                const neutral = row.original.delta === 0;
                const Icon = neutral ? ArrowRight : positive ? TrendingUp : TrendingDown;
                return (
                  <span
                    className={`inline-flex items-center gap-2 ${positive ? "text-green-600 dark:text-green-400" : neutral ? "text-muted-foreground" : "text-red-600 dark:text-red-400"}`}
                  >
                    <Icon className="h-4 w-4" />
                    {`${Math.round(row.original.delta * 100)} pts`}
                  </span>
                );
              },
            },
          ]}
          data={pairedVerdicts}
          emptyStateMessage="No paired verdicts available."
          enableFiltering={false}
          hidePagination
          isLoading={runAVerdictsQuery.isLoading || runBVerdictsQuery.isLoading}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Unique to Run A</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {uniqueToRunA.length > 0 ? uniqueToRunA.map((item) => <p key={item.caseId}>{item.caseName}</p>) : "No unmatched cases."}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Unique to Run B</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            {uniqueToRunB.length > 0 ? uniqueToRunB.map((item) => <p key={item.caseId}>{item.caseName}</p>) : "No unmatched cases."}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
