"use client";

import { format } from "date-fns";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useFleetPerformanceHistory } from "@/lib/hooks/use-fleet-performance";
import {
  PERFORMANCE_TIME_RANGE_LABELS,
  type FleetPerformanceProfile,
  type PerformanceTimeRange,
} from "@/lib/types/fleet";
import { wsClient } from "@/lib/ws";

interface FleetPerformanceChartsProps {
  fleetId: string;
}

function extractRealtimePerformance(payload: unknown): FleetPerformanceProfile | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const candidate =
    "performance_profile" in payload && typeof payload.performance_profile === "object"
      ? payload.performance_profile
      : payload;

  if (!candidate || typeof candidate !== "object") {
    return null;
  }

  const value = candidate as Partial<FleetPerformanceProfile>;
  if (
    typeof value.id !== "string" ||
    typeof value.period_start !== "string" ||
    typeof value.period_end !== "string"
  ) {
    return null;
  }

  return {
    id: value.id,
    fleet_id: value.fleet_id ?? "",
    period_start: value.period_start,
    period_end: value.period_end,
    avg_completion_time_ms: value.avg_completion_time_ms ?? 0,
    success_rate: value.success_rate ?? 0,
    cost_per_task: value.cost_per_task ?? 0,
    avg_quality_score: value.avg_quality_score ?? 0,
    throughput_per_hour: value.throughput_per_hour ?? 0,
    member_metrics: value.member_metrics ?? {},
    flagged_member_fqns: value.flagged_member_fqns ?? [],
  };
}

function mergePerformancePoint(
  current: FleetPerformanceProfile[],
  nextPoint: FleetPerformanceProfile,
): FleetPerformanceProfile[] {
  const withoutCurrent = current.filter((item) => item.id !== nextPoint.id);
  return [...withoutCurrent, nextPoint].sort(
    (left, right) =>
      new Date(left.period_start).getTime() - new Date(right.period_start).getTime(),
  );
}

export function FleetPerformanceCharts({ fleetId }: FleetPerformanceChartsProps) {
  const [range, setRange] = useState<PerformanceTimeRange>("24h");
  const performanceQuery = useFleetPerformanceHistory(fleetId, range);
  const [chartData, setChartData] = useState<FleetPerformanceProfile[]>([]);

  useEffect(() => {
    setChartData(performanceQuery.data ?? []);
  }, [performanceQuery.data]);

  useEffect(() => {
    wsClient.connect();

    return wsClient.subscribe(`fleet:${fleetId}`, (event) => {
      const nextPoint = extractRealtimePerformance(event.payload);
      if (!nextPoint) {
        return;
      }

      setChartData((current) => mergePerformancePoint(current, nextPoint));
    });
  }, [fleetId]);

  const formattedData = useMemo(
    () =>
      chartData.map((item) => ({
        ...item,
        cost: Number(item.cost_per_task.toFixed(2)),
        label: format(new Date(item.period_start), range === "30d" ? "MMM d" : "MMM d, HH:mm"),
        latency: Math.round(item.avg_completion_time_ms),
        successPct: Number((item.success_rate * 100).toFixed(1)),
      })),
    [chartData, range],
  );

  if (performanceQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 rounded-2xl" />
        <div className="grid gap-4 xl:grid-cols-3">
          <Skeleton className="h-72 rounded-3xl" />
          <Skeleton className="h-72 rounded-3xl" />
          <Skeleton className="h-72 rounded-3xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {(Object.entries(PERFORMANCE_TIME_RANGE_LABELS) as [
          PerformanceTimeRange,
          string,
        ][]).map(([value, label]) => (
          <Button
            key={value}
            aria-pressed={range === value}
            size="sm"
            variant={range === value ? "default" : "outline"}
            onClick={() => setRange(value)}
          >
            {label}
          </Button>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <article className="rounded-[1.75rem] border border-border/60 bg-card/80 p-4 shadow-sm">
          <div className="mb-4">
            <h3 className="font-semibold">Success rate</h3>
            <p className="text-sm text-muted-foreground">Task completion reliability over time.</p>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={formattedData} syncId="fleet-perf">
                <CartesianGrid stroke="hsl(var(--border) / 0.45)" strokeDasharray="3 3" />
                <XAxis dataKey="label" minTickGap={28} />
                <YAxis domain={[0, 100]} />
                <RechartsTooltip />
                <Line dataKey="successPct" dot={false} stroke="hsl(var(--brand-primary))" strokeWidth={2.4} type="monotone" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="rounded-[1.75rem] border border-border/60 bg-card/80 p-4 shadow-sm">
          <div className="mb-4">
            <h3 className="font-semibold">Latency</h3>
            <p className="text-sm text-muted-foreground">Average completion time in milliseconds.</p>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={formattedData} syncId="fleet-perf">
                <CartesianGrid stroke="hsl(var(--border) / 0.45)" strokeDasharray="3 3" />
                <XAxis dataKey="label" minTickGap={28} />
                <YAxis />
                <RechartsTooltip />
                <Line dataKey="latency" dot={false} stroke="hsl(var(--warning))" strokeWidth={2.4} type="monotone" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </article>

        <article className="rounded-[1.75rem] border border-border/60 bg-card/80 p-4 shadow-sm">
          <div className="mb-4">
            <h3 className="font-semibold">Cost per task</h3>
            <p className="text-sm text-muted-foreground">Unit cost trend across the selected range.</p>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={formattedData} syncId="fleet-perf">
                <CartesianGrid stroke="hsl(var(--border) / 0.45)" strokeDasharray="3 3" />
                <XAxis dataKey="label" minTickGap={28} />
                <YAxis />
                <RechartsTooltip />
                <Line dataKey="cost" dot={false} stroke="hsl(var(--brand-accent))" strokeWidth={2.4} type="monotone" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </article>
      </div>
    </div>
  );
}

