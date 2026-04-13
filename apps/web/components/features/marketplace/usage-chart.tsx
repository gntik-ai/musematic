"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyUsage } from "@/lib/types/marketplace";

export interface UsageChartProps {
  data: DailyUsage[];
  periodDays: number;
}

export function UsageChart({ data, periodDays }: UsageChartProps) {
  return (
    <div className="space-y-3 rounded-3xl border border-border/60 bg-card/70 p-5">
      <div>
        <p className="text-sm font-semibold">Usage over {periodDays} days</p>
        <p className="text-sm text-muted-foreground">
          Daily invocation volume for this agent.
        </p>
      </div>
      <div className="h-64">
        <ResponsiveContainer height="100%" width="100%">
          <BarChart data={data}>
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="invocations" fill="hsl(var(--chart-1))" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
