"use client";

import { RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";

export function ScoreGauge({
  label,
  score,
  size = 120,
  thresholds = { warning: 40, good: 75 },
}: {
  label?: string;
  score: number;
  size?: 80 | 120 | 160;
  thresholds?: { warning: number; good: number };
}) {
  const color =
    score < thresholds.warning
      ? "hsl(var(--destructive))"
      : score < thresholds.good
        ? "hsl(var(--warning))"
        : "hsl(var(--brand-primary))";

  return (
    <div className="flex flex-col items-center gap-2">
      <div style={{ height: size, width: size }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart cx="50%" cy="50%" data={[{ name: "score", value: score }]} endAngle={-270} innerRadius="75%" outerRadius="100%" startAngle={90}>
            <RadialBar background cornerRadius={999} dataKey="value" fill={color} />
            <text dominantBaseline="middle" fill="currentColor" textAnchor="middle" x="50%" y="50%">
              <tspan className="fill-foreground text-lg font-semibold">{score}</tspan>
            </text>
          </RadialBarChart>
        </ResponsiveContainer>
      </div>
      {label ? <p className="text-sm text-muted-foreground">{label}</p> : null}
    </div>
  );
}
