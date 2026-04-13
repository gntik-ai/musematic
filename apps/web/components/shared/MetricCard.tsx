"use client";

import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { Area, AreaChart, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export type TrendDirection = "up" | "down" | "neutral";

export interface SparklineDataPoint {
  value: number;
  timestamp: string;
}

export interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string | undefined;
  trend?: TrendDirection | undefined;
  trendValue?: string | undefined;
  sparklineData?: SparklineDataPoint[] | undefined;
  isLoading?: boolean | undefined;
  className?: string | undefined;
}

const trendIcon = {
  up: TrendingUp,
  down: TrendingDown,
  neutral: Minus,
} as const;

const trendColor = {
  up: "text-emerald-500",
  down: "text-red-500",
  neutral: "text-muted-foreground",
} as const;

export function MetricCard({
  className,
  isLoading = false,
  sparklineData,
  title,
  trend = "neutral",
  trendValue,
  unit,
  value,
}: MetricCardProps) {
  const TrendIcon = trendIcon[trend];

  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-start justify-between">
        <div>
          <CardTitle className="text-base">{title}</CardTitle>
          {trendValue ? <p className={`mt-2 flex items-center gap-2 text-sm ${trendColor[trend]}`}><TrendIcon className="h-4 w-4" />{trendValue}</p> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <>
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-20 w-full" />
          </>
        ) : (
          <>
            <div className="flex items-end gap-2">
              <span className="text-3xl font-bold">{value}</span>
              {unit ? <span className="pb-1 text-sm text-muted-foreground">{unit}</span> : null}
            </div>
            {sparklineData?.length ? (
              <div className="h-20 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={sparklineData}>
                    <Area
                      dataKey="value"
                      fill="hsl(var(--brand-primary) / 0.2)"
                      stroke="hsl(var(--brand-primary))"
                      strokeWidth={2}
                      type="monotone"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
