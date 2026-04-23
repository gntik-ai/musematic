"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  ComposedChart,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCalibrationScores } from "@/lib/hooks/use-calibration-scores";

export interface CalibrationBoxplotProps {
  suiteId: string;
}

export function CalibrationBoxplot({ suiteId }: CalibrationBoxplotProps) {
  const { scores, isLoading } = useCalibrationScores(suiteId);
  const data = useMemo(
    () =>
      scores.map((score) => ({
        name: score.dimensionName,
        min: score.distribution.min,
        q1: score.distribution.q1,
        median: score.distribution.median,
        q3: score.distribution.q3,
        max: score.distribution.max,
        outlier: score.kappa < 0.6 ? score.distribution.max : null,
        kappaLabel: score.kappa < 0.6 ? `κ = ${score.kappa.toFixed(2)}` : null,
      })),
    [scores],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Calibration box plot</CardTitle>
        <CardDescription>
          Review score distribution spread and highlight low-agreement dimensions.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-[320px] animate-pulse rounded-2xl bg-muted/50" />
        ) : data.length === 0 ? (
          <p className="rounded-xl border border-border/70 bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
            No calibration run is attached to this suite yet.
          </p>
        ) : (
          <div className="h-[320px] w-full">
            <ResponsiveContainer>
              <ComposedChart data={data} margin={{ top: 20, right: 20, bottom: 20, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis domain={[0, 5]} />
                <Tooltip />
                <ReferenceLine y={3} strokeDasharray="4 4" stroke="#64748b" />
                <Scatter dataKey="q1" fill="#94a3b8" />
                <Scatter dataKey="median" fill="#0f172a">
                  <LabelList dataKey="median" position="top" />
                </Scatter>
                <Scatter dataKey="q3" fill="#1d4ed8" />
                <Scatter dataKey="min" fill="#16a34a" />
                <Scatter dataKey="max" fill="#f59e0b" />
                <Scatter dataKey="outlier" fill="#dc2626">
                  <LabelList dataKey="kappaLabel" position="top" />
                </Scatter>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
