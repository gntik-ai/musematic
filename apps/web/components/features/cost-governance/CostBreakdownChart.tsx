"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface CostBreakdownPoint {
  label: string;
  model: number;
  compute: number;
  storage: number;
  overhead: number;
}

interface CostBreakdownChartProps {
  data: CostBreakdownPoint[];
}

const COLORS = {
  model: "hsl(var(--brand-primary))",
  compute: "hsl(var(--chart-2, 173 58% 39%))",
  storage: "hsl(var(--chart-3, 43 96% 56%))",
  overhead: "hsl(var(--chart-4, 280 65% 60%))",
};

export function CostBreakdownChart({ data }: CostBreakdownChartProps) {
  if (data.length === 0) {
    return <div className="flex h-72 items-center justify-center text-sm text-muted-foreground">No cost records</div>;
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" fontSize={12} />
          <YAxis fontSize={12} tickFormatter={(value) => `$${Number(value).toFixed(0)}`} />
          <Tooltip formatter={(value) => `$${Number(value).toFixed(2)}`} />
          <Bar dataKey="model" fill={COLORS.model} stackId="cost" />
          <Bar dataKey="compute" fill={COLORS.compute} stackId="cost" />
          <Bar dataKey="storage" fill={COLORS.storage} stackId="cost" />
          <Bar dataKey="overhead" fill={COLORS.overhead} stackId="cost" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
