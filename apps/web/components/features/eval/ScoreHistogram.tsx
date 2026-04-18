"use client";

import { useMemo } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/shared/EmptyState";
import type { JudgeVerdictResponse, ScoreHistogramBin } from "@/types/evaluation";

export interface ScoreHistogramProps {
  verdicts: JudgeVerdictResponse[];
  height?: number | undefined;
}

function buildBins(verdicts: JudgeVerdictResponse[]): ScoreHistogramBin[] {
  const bins = Array.from({ length: 10 }, (_, index) => ({
    rangeLabel: `${(index / 10).toFixed(1)}–${((index + 1) / 10).toFixed(1)}`,
    min: index / 10,
    max: (index + 1) / 10,
    count: 0,
  }));

  verdicts.forEach((verdict) => {
    if (typeof verdict.overall_score !== "number") {
      return;
    }

    const binIndex = Math.min(Math.floor(verdict.overall_score * 10), 9);
    const targetBin = bins[binIndex];
    if (targetBin) {
      targetBin.count += 1;
    }
  });

  return bins;
}

export function ScoreHistogram({
  verdicts,
  height = 200,
}: ScoreHistogramProps) {
  const bins = useMemo(() => buildBins(verdicts), [verdicts]);
  const hasScores = bins.some((bin) => bin.count > 0);

  if (!hasScores) {
    return (
      <EmptyState
        description="This run has no scored verdicts yet."
        title="No scores available"
      />
    );
  }

  return (
    <div
      aria-label="Score distribution histogram"
      className="rounded-2xl border border-border/70 bg-card/80 p-4"
    >
      <div className="mb-3">
        <h3 className="text-lg font-semibold">Score distribution</h3>
        <p className="text-sm text-muted-foreground">
          Verdict scores grouped into ten equal-width bands.
        </p>
      </div>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={bins}>
            <XAxis dataKey="rangeLabel" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
            <Tooltip
              formatter={(value: number) => [`${value}`, "Cases"]}
              labelFormatter={(label) => `Score range ${label}`}
            />
            <Bar dataKey="count" fill="hsl(var(--brand-primary))" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
