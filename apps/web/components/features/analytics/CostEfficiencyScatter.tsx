"use client";

import type { ReactElement } from "react";
import {
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  type TooltipProps,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/shared/EmptyState";
import { formatUsd } from "@/lib/analytics";
import type { ScatterPoint } from "@/types/analytics";

export interface CostEfficiencyScatterProps {
  agents: ScatterPoint[];
  onAgentClick?: (agent: ScatterPoint, position: { x: number; y: number }) => void;
  height?: number;
}

function CustomScatterShape(props: {
  cx?: number | undefined;
  cy?: number | undefined;
  payload?: ScatterPoint | undefined;
  onAgentClick?:
    | ((agent: ScatterPoint, position: { x: number; y: number }) => void)
    | undefined;
}): ReactElement {
  const cx = typeof props.cx === "number" ? props.cx : 0;
  const cy = typeof props.cy === "number" ? props.cy : 0;
  const payload = props.payload;
  const onAgentClick = props.onAgentClick;

  if (!payload) {
    return <circle cx={cx} cy={cy} fill="transparent" r={0} />;
  }

  return (
    <circle
      cx={cx}
      cy={cy}
      fill={
        payload.hasQualityData
          ? "hsl(var(--brand-primary))"
          : "hsl(var(--muted-foreground) / 0.2)"
      }
      fillOpacity={payload.hasQualityData ? 0.85 : 0.3}
      onClick={() => onAgentClick?.(payload, { x: cx, y: cy })}
      r={payload.hasQualityData ? 7 : 8}
      stroke="hsl(var(--brand-primary))"
      strokeDasharray={payload.hasQualityData ? undefined : "4 2"}
      strokeWidth={2}
      style={{ cursor: onAgentClick ? "pointer" : "default" }}
    />
  );
}

function NoQualityLabel(props: {
  payload?: ScatterPoint | undefined;
  x?: number | string | undefined;
  y?: number | string | undefined;
}): ReactElement | null {
  if (props.payload?.hasQualityData ?? true) {
    return null;
  }

  const x = typeof props.x === "number" ? props.x : 0;
  const y = typeof props.y === "number" ? props.y : 0;

  return (
    <text
      fill="hsl(var(--muted-foreground))"
      fontSize={11}
      textAnchor="middle"
      x={x}
      y={y - 12}
    >
      No quality data
    </text>
  );
}

export function CostEfficiencyScatter({
  agents,
  onAgentClick,
  height = 400,
}: CostEfficiencyScatterProps) {
  if (agents.length === 0) {
    return (
      <EmptyState
        description="Efficiency insights will appear after enough quality and spend data accumulates."
        title="No efficiency data"
      />
    );
  }

  const chartData = agents.map((agent) => ({
    ...agent,
    qualityScore: agent.qualityScore ?? 0,
  }));

  return (
    <div aria-label="Cost efficiency scatter chart" className="h-[400px] w-full" role="img">
      <ResponsiveContainer height={height} width="100%">
        <ScatterChart margin={{ top: 12, right: 12, bottom: 12, left: 12 }}>
          <CartesianGrid stroke="hsl(var(--border) / 0.45)" strokeDasharray="3 3" />
          <XAxis
            dataKey="costUsd"
            name="Cost (USD)"
            tickFormatter={(value: number) => formatUsd(value)}
            type="number"
          />
          <YAxis
            dataKey="qualityScore"
            domain={[0, 1]}
            name="Quality score"
            tickFormatter={(value: number) => value.toFixed(2)}
            type="number"
          />
          <Tooltip
            cursor={{ strokeDasharray: "4 4" }}
            content={(tooltipProps: TooltipProps<number, string>) => {
              if (!tooltipProps.active) {
                return null;
              }

              const payload = tooltipProps.payload?.[0]?.payload as ScatterPoint | undefined;
              if (!payload) {
                return null;
              }

              return (
                <div className="rounded-xl border border-border/60 bg-background/95 px-3 py-2 shadow-lg">
                  <p className="font-medium">{payload.agentFqn}</p>
                  <p className="text-sm text-muted-foreground">
                    Cost: {formatUsd(payload.costUsd)}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Quality: {payload.hasQualityData ? payload.qualityScore?.toFixed(2) : "No quality data"}
                  </p>
                </div>
              );
            }}
          />
          <Scatter
            data={chartData}
            shape={(props: unknown) => (
              <CustomScatterShape
                {...(props as {
                  cx?: number | undefined;
                  cy?: number | undefined;
                  payload?: ScatterPoint | undefined;
                })}
                onAgentClick={onAgentClick}
              />
            )}
          >
            <LabelList
              content={(props: unknown) =>
                NoQualityLabel(
                  props as {
                    payload?: ScatterPoint | undefined;
                    x?: number | string | undefined;
                    y?: number | string | undefined;
                  },
                )
              }
              dataKey="agentFqn"
            />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
