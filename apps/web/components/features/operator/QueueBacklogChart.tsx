"use client";

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SectionError } from "@/components/features/home/SectionError";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { QueueTopicLag } from "@/lib/types/operator-dashboard";

export interface QueueBacklogChartProps {
  data: QueueTopicLag[];
  isLoading: boolean;
  error?: boolean;
}

function abbreviateTopic(topic: string): string {
  return topic.length > 16 ? `${topic.slice(0, 13)}…` : topic;
}

export function QueueBacklogChart({
  data,
  isLoading,
  error = false,
}: QueueBacklogChartProps) {
  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Queue backlog</CardTitle>
        <p className="text-sm text-muted-foreground">
          Consumer lag across high-signal orchestration topics.
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[280px] rounded-xl" />
        ) : error ? (
          <SectionError
            message="Backlog data unavailable"
            onRetry={() => {
              window.location.reload();
            }}
            title="Queue lag unavailable"
          />
        ) : data.length === 0 ? (
          <EmptyState
            description="No lag snapshot is currently available."
            title="Backlog data unavailable"
          />
        ) : (
          <div className="h-[280px] w-full">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={data}>
                <XAxis dataKey="topic" tickFormatter={abbreviateTopic} />
                <YAxis allowDecimals={false} />
                <Tooltip
                  formatter={(value: number, _name, item) => [
                    `${value} lag${item.payload.warning ? " · ⚠ High lag" : ""}`,
                    item.payload.topic,
                  ]}
                />
                <Bar dataKey="lag" radius={[8, 8, 0, 0]}>
                  {data.map((topic) => (
                    <Cell
                      key={topic.topic}
                      fill={
                        topic.warning
                          ? "hsl(var(--warning))"
                          : "hsl(var(--brand-primary))"
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
