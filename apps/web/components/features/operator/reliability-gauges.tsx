"use client";

import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useReliabilityGauges } from "@/lib/hooks/use-reliability-gauges";

const LABELS: Record<string, string> = {
  api: "API",
  execution: "Execution",
  event_delivery: "Event delivery",
};

function tone(percent: number): string {
  if (percent >= 99.5) {
    return "#15803d";
  }
  if (percent >= 99) {
    return "#d97706";
  }
  return "#dc2626";
}

export interface ReliabilityGaugesProps {
  windowDays?: number;
}

export function ReliabilityGauges({ windowDays }: ReliabilityGaugesProps) {
  const { gauges } = useReliabilityGauges(windowDays);

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {gauges.map((gauge) => (
        <Card key={gauge.id}>
          <CardHeader>
            <CardTitle>{LABELS[gauge.id] ?? gauge.id}</CardTitle>
          </CardHeader>
          <CardContent className="h-[220px]">
            <ResponsiveContainer>
              <RadialBarChart cx="50%" cy="50%" data={[gauge]} endAngle={90} innerRadius="55%" outerRadius="100%" startAngle={-270}>
                <PolarAngleAxis domain={[0, 100]} tick={false} type="number" />
                <RadialBar background cornerRadius={12} dataKey="availabilityPercent" fill={tone(gauge.availabilityPercent)} />
                <text dominantBaseline="middle" textAnchor="middle" x="50%" y="50%">
                  <tspan className="fill-foreground text-2xl font-semibold" x="50%" dy="-0.2em">
                    {gauge.availabilityPercent.toFixed(2)}%
                  </tspan>
                  <tspan className="fill-muted-foreground text-xs" x="50%" dy="1.8em">
                    {gauge.windowDays}d window
                  </tspan>
                </text>
              </RadialBarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
