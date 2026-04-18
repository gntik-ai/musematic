"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/shared/EmptyState";
import { analyticsColorAt, formatCompactNumber, humanizeAnalyticsKey, median } from "@/lib/analytics";
import type { TokenBarPoint } from "@/types/analytics";

export interface TokenConsumptionChartProps {
  data: TokenBarPoint[];
  providers: string[];
  height?: number;
}

function getOutlierThreshold(data: TokenBarPoint[], providers: string[]): number | null {
  const totals = data.map((point) =>
    providers.reduce((sum, provider) => {
      const value = point[provider];
      return sum + (typeof value === "number" ? value : 0);
    }, 0),
  );
  const baseline = median(totals);
  if (baseline <= 0) {
    return null;
  }

  const threshold = baseline * 3;
  return totals.some((value) => value > threshold) ? threshold : null;
}

export function TokenConsumptionChart({
  data,
  providers,
  height = 280,
}: TokenConsumptionChartProps) {
  const outlierThreshold = getOutlierThreshold(data, providers);

  if (data.length === 0 || providers.length === 0) {
    return (
      <EmptyState
        description="Token usage will appear here when providers start reporting traffic."
        title="No token data"
      />
    );
  }

  return (
    <div aria-label="Token consumption chart" className="h-[280px] w-full" role="img">
      <ResponsiveContainer height={height} width="100%">
        <BarChart data={data}>
          <CartesianGrid stroke="hsl(var(--border) / 0.45)" strokeDasharray="3 3" />
          <XAxis dataKey="period" minTickGap={24} />
          <YAxis tickFormatter={(value: number) => formatCompactNumber(value)} />
          <Tooltip
            formatter={(value: number, name: string) => [
              `${formatCompactNumber(value)} tokens`,
              humanizeAnalyticsKey(name),
            ]}
          />
          <Legend formatter={(value) => humanizeAnalyticsKey(String(value))} />
          {outlierThreshold !== null ? (
            <ReferenceLine
              label="Outlier threshold"
              stroke="hsl(var(--warning))"
              strokeDasharray="4 4"
              y={outlierThreshold}
            />
          ) : null}
          {providers.map((provider, index) => (
            <Bar
              key={provider}
              dataKey={provider}
              fill={analyticsColorAt(index)}
              radius={index === providers.length - 1 ? [8, 8, 0, 0] : 0}
              stackId="tokens"
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
