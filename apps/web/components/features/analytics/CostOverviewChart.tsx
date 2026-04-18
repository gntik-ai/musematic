"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { analyticsColorAt, formatUsd, humanizeAnalyticsKey, median } from "@/lib/analytics";
import {
  BREAKDOWN_MODE_LABELS,
  type BreakdownMode,
  type CostChartPoint,
} from "@/types/analytics";

export interface CostOverviewChartProps {
  data: CostChartPoint[];
  seriesKeys: string[];
  breakdownMode: BreakdownMode;
  onBreakdownChange: (mode: BreakdownMode) => void;
  height?: number;
}

const breakdownModes = ["workspace", "agent", "model"] as const satisfies BreakdownMode[];

function getOutlierThreshold(
  data: CostChartPoint[],
  seriesKeys: string[],
): number | null {
  const values = data.flatMap((point) =>
    seriesKeys
      .map((key) => point[key])
      .filter((value): value is number => typeof value === "number"),
  );
  const baseline = median(values);
  if (baseline <= 0) {
    return null;
  }

  const threshold = baseline * 3;
  return values.some((value) => value > threshold) ? threshold : null;
}

export function CostOverviewChart({
  data,
  seriesKeys,
  breakdownMode,
  onBreakdownChange,
  height = 320,
}: CostOverviewChartProps) {
  const outlierThreshold = getOutlierThreshold(data, seriesKeys);

  const handleBreakdownKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    currentMode: BreakdownMode,
  ) => {
    const currentIndex = breakdownModes.indexOf(currentMode);
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
      return;
    }

    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex =
      (currentIndex + direction + breakdownModes.length) % breakdownModes.length;
    onBreakdownChange(breakdownModes[nextIndex] ?? "workspace");
  };

  if (data.length === 0 || seriesKeys.length === 0) {
    return (
      <EmptyState
        description="Cost trend lines will appear after analytics usage data is available."
        title="No cost data"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div
        aria-label="Cost breakdown selector"
        className="flex flex-wrap gap-2"
        role="group"
      >
        {breakdownModes.map((mode) => (
          <Button
            key={mode}
            aria-pressed={breakdownMode === mode}
            size="sm"
            tabIndex={0}
            variant={breakdownMode === mode ? "default" : "outline"}
            onKeyDown={(event) => handleBreakdownKeyDown(event, mode)}
            onClick={() => onBreakdownChange(mode)}
          >
            {BREAKDOWN_MODE_LABELS[mode]}
          </Button>
        ))}
      </div>

      <div
        aria-label="Cost over time chart"
        className="h-[320px] w-full"
        role="img"
      >
        <ResponsiveContainer height={height} width="100%">
          <LineChart data={data}>
            <CartesianGrid stroke="hsl(var(--border) / 0.45)" strokeDasharray="3 3" />
            <XAxis dataKey="period" minTickGap={24} />
            <YAxis tickFormatter={(value: number) => formatUsd(value)} width={88} />
            <Tooltip
              formatter={(value: number, name: string) => [formatUsd(value), humanizeAnalyticsKey(name)]}
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
            {seriesKeys.map((seriesKey, index) => (
              <Line
                key={seriesKey}
                dataKey={seriesKey}
                dot={false}
                name={humanizeAnalyticsKey(seriesKey)}
                stroke={analyticsColorAt(index)}
                strokeWidth={2.4}
                type="monotone"
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
