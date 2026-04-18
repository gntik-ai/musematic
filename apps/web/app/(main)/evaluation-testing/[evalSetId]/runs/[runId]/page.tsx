"use client";

import Link from "next/link";
import { use, useState } from "react";
import { EvalRunDetail } from "@/components/features/eval/EvalRunDetail";
import { useEvalSetCases, useEvalRunVerdicts } from "@/lib/hooks/use-eval-verdicts";
import { useEvalRun } from "@/lib/hooks/use-eval-runs";
import { useEvalSet } from "@/lib/hooks/use-eval-sets";

interface EvalRunDetailPageProps {
  params: Promise<{
    evalSetId: string;
    runId: string;
  }>;
}

export default function EvalRunDetailPage({ params }: EvalRunDetailPageProps) {
  const { evalSetId, runId } = use(params);
  const [page, setPage] = useState(1);
  const suiteQuery = useEvalSet(evalSetId);
  const runQuery = useEvalRun(runId);
  const verdictsQuery = useEvalRunVerdicts(runId, page);
  const casesQuery = useEvalSetCases(evalSetId, page);

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <nav className="text-sm text-muted-foreground">
          <Link className="underline-offset-4 hover:underline" href="/evaluation-testing">
            Eval Suites
          </Link>
          {" → "}
          <Link
            className="underline-offset-4 hover:underline"
            href={`/evaluation-testing/${encodeURIComponent(evalSetId)}`}
          >
            {suiteQuery.data?.name ?? "Suite"}
          </Link>
          {" → "}
          <span>Run {runId.slice(0, 8)}</span>
        </nav>
        <h1 className="text-3xl font-semibold tracking-tight">Run Detail</h1>
      </div>

      {runQuery.data ? (
        <EvalRunDetail
          cases={casesQuery.data?.items ?? []}
          onPageChange={setPage}
          page={page}
          run={runQuery.data}
          total={verdictsQuery.data?.total ?? 0}
          verdicts={verdictsQuery.data?.items ?? []}
        />
      ) : (
        <div className="rounded-2xl border border-border/70 bg-card/80 p-6 text-sm text-muted-foreground">
          Loading run detail…
        </div>
      )}
    </section>
  );
}
