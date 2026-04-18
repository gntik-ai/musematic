"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { AggregateMetrics } from "@/components/features/eval/AggregateMetrics";
import { ScoreHistogram } from "@/components/features/eval/ScoreHistogram";
import { VerdictTable } from "@/components/features/eval/VerdictTable";
import type {
  BenchmarkCaseResponse,
  EvaluationRunResponse,
  JudgeVerdictResponse,
} from "@/types/evaluation";

export interface EvalRunDetailProps {
  run: EvaluationRunResponse;
  verdicts: JudgeVerdictResponse[];
  cases: BenchmarkCaseResponse[];
  total: number;
  page: number;
  onPageChange: (page: number) => void;
}

export function EvalRunDetail({
  run,
  verdicts,
  cases,
  total,
  page,
  onPageChange,
}: EvalRunDetailProps) {
  return (
    <section className="space-y-6">
      <AggregateMetrics run={run} />

      {run.status === "completed" ? (
        <>
          <VerdictTable
            cases={cases}
            onPageChange={onPageChange}
            page={page}
            total={total}
            verdicts={verdicts}
          />
          <ScoreHistogram verdicts={verdicts} />
        </>
      ) : null}

      {run.status === "pending" || run.status === "running" ? (
        <div
          aria-busy="true"
          className="space-y-3 rounded-2xl border border-border/70 bg-card/80 p-5"
        >
          <div>
            <h3 className="text-lg font-semibold">Evaluation in progress…</h3>
            <p className="text-sm text-muted-foreground">
              This run is still processing benchmark cases. Results refresh automatically.
            </p>
          </div>
          <Progress value={run.status === "running" ? 65 : 20} />
        </div>
      ) : null}

      {run.status === "failed" ? (
        <Alert variant="destructive">
          <AlertTitle>Evaluation failed</AlertTitle>
          <AlertDescription>{run.error_detail ?? "The run did not complete."}</AlertDescription>
        </Alert>
      ) : null}
    </section>
  );
}
