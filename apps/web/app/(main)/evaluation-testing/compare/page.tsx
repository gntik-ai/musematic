"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { EvalComparisonView } from "@/components/features/eval/EvalComparisonView";
import { useEvalMutations } from "@/lib/hooks/use-eval-mutations";

export default function EvalComparisonPage() {
  const searchParams = useSearchParams();
  const runA = searchParams.get("runA");
  const runB = searchParams.get("runB");
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const { createExperiment } = useEvalMutations();

  useEffect(() => {
    if (!runA || !runB || experimentId || createExperiment.isPending) {
      return;
    }

    void createExperiment
      .mutateAsync({
        runAId: runA,
        runBId: runB,
        name: `Compare ${runA} vs ${runB}`,
      })
      .then((experiment) => setExperimentId(experiment.id));
  }, [createExperiment, experimentId, runA, runB]);

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <Link
          className="text-sm text-muted-foreground underline-offset-4 hover:underline"
          href="/evaluation-testing"
        >
          Back to Eval Suites
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">Eval Comparison</h1>
      </div>
      {experimentId ? (
        <EvalComparisonView experimentId={experimentId} runAId={runA ?? ""} runBId={runB ?? ""} />
      ) : (
        <div className="rounded-2xl border border-border/70 bg-card/80 p-6 text-sm text-muted-foreground">
          Creating comparison…
        </div>
      )}
    </section>
  );
}
