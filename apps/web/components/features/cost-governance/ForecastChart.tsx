"use client";

import {
  Area,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CostForecastResponse } from "@/lib/api/costs";

interface ForecastChartProps {
  forecast?: CostForecastResponse | null;
}

export function ForecastChart({ forecast }: ForecastChartProps) {
  const status = String(forecast?.confidence_interval?.status ?? "");
  if (!forecast || status === "insufficient_history" || forecast.forecast_cents === null) {
    return <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">Insufficient history</div>;
  }

  const low = Number(forecast.confidence_interval.low_cents ?? forecast.forecast_cents) / 100;
  const high = Number(forecast.confidence_interval.high_cents ?? forecast.forecast_cents) / 100;
  const value = Number(forecast.forecast_cents) / 100;
  const data = [
    { label: "Low", value: low, band: high - low },
    { label: "Forecast", value, band: Math.max(high - value, 0) },
  ];

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" fontSize={12} />
          <YAxis fontSize={12} tickFormatter={(item) => `$${Number(item).toFixed(0)}`} />
          <Tooltip formatter={(item) => `$${Number(item).toFixed(2)}`} />
          <Area dataKey="band" fill="hsl(var(--brand-primary) / 0.14)" stroke="transparent" />
          <Line dataKey="value" stroke="hsl(var(--brand-primary))" strokeWidth={2} type="monotone" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
