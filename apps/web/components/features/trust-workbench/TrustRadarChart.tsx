"use client";

import type { ComponentProps } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  toTrustRadarChartData,
  TRUST_DIMENSION_LABELS,
  type TrustRadarProfile,
} from "@/lib/types/trust-workbench";
import { TrustDimensionTooltip } from "@/components/features/trust-workbench/TrustDimensionTooltip";

export interface TrustRadarChartProps {
  profile: TrustRadarProfile;
  className?: string;
}

export function TrustRadarChart({
  profile,
  className,
}: TrustRadarChartProps) {
  const chartData = toTrustRadarChartData(profile);

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Trust radar</CardTitle>
      </CardHeader>
      <CardContent>
        <div
          aria-label={`Trust radar chart for ${profile.agentFqn}`}
          className="min-h-[320px] w-full"
          role="img"
        >
          <ResponsiveContainer height="100%" width="100%">
            <RadarChart data={chartData}>
              <PolarGrid gridType="polygon" stroke="hsl(var(--border))" />
              <PolarAngleAxis
                dataKey="subject"
                tick={({ payload, x, y, textAnchor }) => {
                  const point = chartData.find(
                    (entry) => entry.subject === payload.value,
                  );
                  const label = payload.value as string;

                  return (
                    <text
                      fill="hsl(var(--foreground))"
                      fontSize={12}
                      textAnchor={textAnchor}
                      x={x}
                      y={y}
                    >
                      {point?.isWeak ? `${label} !` : label}
                    </text>
                  );
                }}
              />
              <PolarRadiusAxis
                axisLine={false}
                domain={[0, 100]}
                stroke="hsl(var(--muted-foreground))"
                tickCount={5}
              />
              <Radar
                dataKey="score"
                dot={(props) => {
                  const payload = props.payload as { isWeak?: boolean } | undefined;

                  return (
                    <circle
                      cx={props.cx}
                      cy={props.cy}
                      fill={payload?.isWeak ? "rgba(251, 191, 36, 0.7)" : "hsl(var(--brand-accent))"}
                      r={payload?.isWeak ? 5 : 3.5}
                      stroke="transparent"
                    />
                  );
                }}
                fill="hsl(var(--brand-accent) / 0.18)"
                fillOpacity={1}
                stroke="hsl(var(--brand-accent))"
                strokeWidth={2}
              />
              <RechartsTooltip
                content={(tooltipProps) => (
                  <TrustDimensionTooltip
                    active={tooltipProps.active}
                    dimensionScores={profile.dimensions}
                    payload={
                      tooltipProps.payload as TrustDimensionTooltipProps["payload"]
                    }
                  />
                )}
              />
            </RadarChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {profile.dimensions.map((dimension) => (
            <div
              key={dimension.dimension}
              className="rounded-2xl border border-border/60 bg-background/70 px-4 py-3"
            >
              <p className="text-sm font-medium">
                {TRUST_DIMENSION_LABELS[dimension.dimension]}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {dimension.score} / 100
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

type TrustDimensionTooltipProps = ComponentProps<typeof TrustDimensionTooltip>;
