"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { WeeklyRating } from "@/lib/types/marketplace";

export interface SatisfactionTrendChartProps {
  data: WeeklyRating[];
}

export function SatisfactionTrendChart({
  data,
}: SatisfactionTrendChartProps) {
  return (
    <div className="space-y-3 rounded-3xl border border-border/60 bg-card/70 p-5">
      <div>
        <p className="text-sm font-semibold">Satisfaction trend</p>
        <p className="text-sm text-muted-foreground">
          Weekly average rating trend across recent reviews.
        </p>
      </div>
      <div className="h-64">
        <ResponsiveContainer height="100%" width="100%">
          <LineChart data={data}>
            <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
            <XAxis dataKey="weekStart" tick={{ fontSize: 12 }} />
            <YAxis domain={[0, 5]} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Line
              connectNulls={false}
              dataKey="averageRating"
              dot={{ r: 3 }}
              stroke="hsl(var(--chart-2))"
              strokeWidth={3}
              type="monotone"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
