"use client";

import type { ReactElement } from "react";
import {
  CartesianGrid,
  Customized,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  type TooltipProps,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/shared/EmptyState";
import type { DriftChartPoint } from "@/types/analytics";

export interface DriftChartProps {
  agentFqn: string;
  data: DriftChartPoint[];
  height?: number;
}

function EmptyDriftAnnotation(): ReactElement {
  return (
    <text
      fill="hsl(var(--muted-foreground))"
      fontSize={13}
      textAnchor="middle"
      x="50%"
      y="50%"
    >
      No drift detected
    </text>
  );
}

function renderAnomalyDot(props: {
  payload?: DriftChartPoint;
  cx?: number;
  cy?: number;
}): ReactElement {
  if (!(props.payload?.isAnomaly ?? false)) {
    return <circle cx={0} cy={0} fill="transparent" r={0} />;
  }

  const cx = typeof props.cx === "number" ? props.cx : 0;
  const cy = typeof props.cy === "number" ? props.cy : 0;

  return (
    <circle
      cx={cx}
      cy={cy}
      fill="hsl(var(--destructive))"
      r={6}
      stroke="hsl(var(--background))"
      strokeWidth={2}
    />
  );
}

export function DriftChart({
  agentFqn,
  data,
  height = 220,
}: DriftChartProps) {
  if (data.length === 0) {
    return (
      <EmptyState
        description="No drift markers have been recorded for this agent."
        title={agentFqn}
      />
    );
  }

  const baseline = data.find((point) => Number.isFinite(point.baseline))?.baseline ?? 0;
  const hasAnomaly = data.some((point) => point.isAnomaly);

  return (
    <div className="space-y-3 rounded-[1.5rem] border border-border/60 bg-card/80 p-4">
      <div>
        <h3 className="font-semibold">{agentFqn}</h3>
        <p className="text-sm text-muted-foreground">
          Behavioral drift against the historical baseline.
        </p>
      </div>
      <div aria-label={`Drift chart for ${agentFqn}`} className="h-[220px] w-full" role="img">
        <ResponsiveContainer height={height} width="100%">
          <LineChart data={data}>
            <CartesianGrid stroke="hsl(var(--border) / 0.45)" strokeDasharray="3 3" />
            <XAxis dataKey="period" minTickGap={24} />
            <YAxis domain={[0, "auto"]} />
            <Tooltip
              content={(tooltipProps: TooltipProps<number, string>) => {
                if (!tooltipProps.active) {
                  return null;
                }

                const point = tooltipProps.payload?.[0]?.payload as
                  | DriftChartPoint
                  | undefined;
                if (!point) {
                  return null;
                }

                const deviation =
                  point.value === null ? null : point.value - point.baseline;

                return (
                  <div className="rounded-xl border border-border/60 bg-background/95 px-3 py-2 shadow-lg">
                    <p className="font-medium">{point.period}</p>
                    <p className="text-sm text-muted-foreground">
                      Actual: {point.value === null ? "—" : point.value.toFixed(2)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Baseline: {point.baseline.toFixed(2)}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Deviation: {deviation === null ? "—" : deviation.toFixed(2)}
                    </p>
                  </div>
                );
              }}
            />
            <ReferenceLine
              label="Baseline"
              stroke="hsl(var(--muted-foreground))"
              strokeDasharray="4 2"
              y={baseline}
            />
            <Line
              connectNulls
              dataKey="value"
              dot={renderAnomalyDot}
              stroke="hsl(var(--brand-primary))"
              strokeWidth={2.4}
              type="monotone"
            />
            {!hasAnomaly ? <Customized component={EmptyDriftAnnotation} /> : null}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
