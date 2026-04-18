"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { formatUsd } from "@/lib/analytics";
import type { ForecastChartPoint } from "@/types/analytics";

export interface ForecastChartProps {
  data: ForecastChartPoint[];
  trendDirection: string;
  totalProjectedExpected: number;
  height?: number;
}

const trendIcon = {
  increasing: TrendingUp,
  decreasing: TrendingDown,
  stable: Minus,
} as const;

export function ForecastChart({
  data,
  trendDirection,
  totalProjectedExpected,
  height = 300,
}: ForecastChartProps) {
  if (data.length === 0) {
    return (
      <EmptyState
        description="Forecast projections will appear when there is enough historical spend."
        title="No forecast data"
      />
    );
  }

  const TrendIcon = trendIcon[trendDirection as keyof typeof trendIcon] ?? Minus;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <TrendIcon className="h-4 w-4 text-brand-accent" />
          <span>{trendDirection}</span>
        </div>
        <p className="text-sm font-medium">
          Expected total: {formatUsd(totalProjectedExpected)}
        </p>
      </div>

      <div aria-label="Cost forecast chart" className="h-[300px] w-full" role="img">
        <ResponsiveContainer height={height} width="100%">
          <ComposedChart data={data}>
            <CartesianGrid stroke="hsl(var(--border) / 0.45)" strokeDasharray="3 3" />
            <XAxis dataKey="date" minTickGap={24} />
            <YAxis tickFormatter={(value: number) => formatUsd(value)} width={88} />
            <Tooltip
              formatter={(value: number, name: string) => [formatUsd(value), name]}
            />
            <Legend />
            <Area
              dataKey="low"
              fill="hsl(var(--brand-accent) / 0.05)"
              stroke="hsl(var(--brand-accent) / 0.2)"
              type="monotone"
            />
            <Area
              dataKey="high"
              fill="hsl(var(--brand-primary) / 0.15)"
              stroke="hsl(var(--brand-primary) / 0.3)"
              type="monotone"
            />
            <Line
              dataKey="low"
              dot={false}
              name="Low projection"
              stroke="hsl(var(--brand-accent))"
              strokeDasharray="4 3"
              strokeWidth={1.8}
              type="monotone"
            />
            <Line
              dataKey="high"
              dot={false}
              name="High projection"
              stroke="hsl(var(--brand-primary) / 0.75)"
              strokeDasharray="4 3"
              strokeWidth={1.8}
              type="monotone"
            />
            <Line
              dataKey="expected"
              dot={false}
              name="Expected projection"
              stroke="hsl(var(--brand-primary))"
              strokeWidth={2.5}
              type="monotone"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
