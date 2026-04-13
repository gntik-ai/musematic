"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/shared/EmptyState";
import { Alert } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import type { SelfCorrectionIteration, SelfCorrectionLoop } from "@/types/reasoning";

function IterationDetail({ iteration }: { iteration: SelfCorrectionIteration }) {
  return (
    <Alert className="border-border/70 bg-card/80">
      <div className="space-y-1">
        <p className="font-medium">Iteration {iteration.iterationNumber}</p>
        <p className="text-sm text-muted-foreground">
          Quality {iteration.qualityScore.toFixed(2)} · Delta {iteration.delta.toFixed(2)}
        </p>
        <p className="text-sm text-muted-foreground">
          {iteration.tokenCost} tokens · {iteration.durationMs} ms
        </p>
        {iteration.thoughts ? (
          <p className="text-sm text-foreground">{iteration.thoughts}</p>
        ) : null}
      </div>
    </Alert>
  );
}

export function SelfCorrectionChart({
  isLoading,
  loop,
  selectedIterationNumber,
  onSelectIteration,
}: {
  isLoading?: boolean;
  loop: SelfCorrectionLoop | null | undefined;
  selectedIterationNumber?: number | null;
  onSelectIteration?: (iterationNumber: number) => void;
}) {
  if (isLoading) {
    return <Skeleton className="h-[320px] rounded-xl" />;
  }

  if (!loop || loop.iterations.length === 0) {
    return (
      <EmptyState
        description="This step did not emit any self-correction iterations."
        title="No self-correction iterations for this step"
      />
    );
  }

  const selectedIteration =
    loop.iterations.find(
      (iteration) => iteration.iterationNumber === selectedIterationNumber,
    ) ?? loop.iterations.at(-1);
  const referenceIteration = loop.iterations.at(-1)?.iterationNumber;

  return (
    <div className="space-y-4">
      <div className="h-[320px] rounded-2xl border border-border/70 bg-card/80 p-4">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={loop.iterations}
            onClick={(state) => {
              const payload = state.activePayload?.[0]?.payload as
                | SelfCorrectionIteration
                | undefined;
              if (payload) {
                onSelectIteration?.(payload.iterationNumber);
              }
            }}
            margin={{ top: 12, right: 12, left: 0, bottom: 0 }}
          >
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
            <XAxis dataKey="iterationNumber" />
            <YAxis domain={[0, 1]} />
            <Tooltip />
            {referenceIteration !== undefined ? (
              <ReferenceLine
                label={
                  loop.finalStatus === "converged"
                    ? "Converged"
                    : "Budget limit"
                }
                stroke={
                  loop.finalStatus === "converged"
                    ? "hsl(var(--brand-primary))"
                    : "hsl(var(--destructive))"
                }
                strokeDasharray="4 4"
                x={referenceIteration}
              />
            ) : null}
            <Line
              activeDot={{ r: 6 }}
              dataKey="qualityScore"
              dot={{ r: 4 }}
              stroke="hsl(var(--brand-primary))"
              strokeWidth={2}
              type="monotone"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {selectedIteration ? <IterationDetail iteration={selectedIteration} /> : null}
    </div>
  );
}
