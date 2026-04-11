"use client";

import { useMemo } from "react";
import { formatDistanceToNow } from "date-fns";
import { Activity, Sparkles } from "lucide-react";
import { Timeline, type TimelineEvent } from "@/components/shared/Timeline";
import { SectionError } from "@/components/features/home/SectionError";
import { useRecentActivity } from "@/lib/hooks/use-home-data";
import type { ActivityEntry } from "@/lib/types/home";

interface RecentActivityProps {
  workspaceId: string;
  isConnected?: boolean;
}

function toTimelineStatus(entry: ActivityEntry): TimelineEvent["status"] {
  switch (entry.status) {
    case "completed":
      return "healthy";
    case "failed":
      return "error";
    case "canceled":
      return "inactive";
    case "waiting":
      return "pending";
    case "running":
    default:
      return "running";
  }
}

function buildDescription(entry: ActivityEntry): string | undefined {
  if (entry.type === "interaction" && entry.metadata?.agent_fqn) {
    return `Agent ${entry.metadata.agent_fqn}`;
  }

  if (entry.type === "execution" && entry.metadata?.workflow_name) {
    return `Workflow ${entry.metadata.workflow_name}`;
  }

  return undefined;
}

export function RecentActivity({
  workspaceId,
  isConnected,
}: RecentActivityProps) {
  const { data, error, isError, isLoading, refetch } = useRecentActivity(
    workspaceId,
    { isConnected },
  );

  const events = useMemo<TimelineEvent[]>(() => {
    return [...(data?.items ?? [])]
      .sort((left, right) =>
        new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime(),
      )
      .slice(0, 10)
      .map((entry) => ({
        id: entry.id,
        timestamp: entry.timestamp,
        timestampLabel: formatDistanceToNow(new Date(entry.timestamp), {
          addSuffix: true,
        }),
        label: entry.title,
        description: buildDescription(entry),
        href: entry.href,
        status: toTimelineStatus(entry),
      }));
  }, [data?.items]);

  if (isError) {
    return (
      <SectionError
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => {
          void refetch();
        }}
        title="Recent activity unavailable"
      />
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2">
        <Activity className="h-4 w-4 text-brand-accent" />
        <h2 className="text-lg font-semibold">Recent activity</h2>
      </div>
      <Timeline
        emptyDescription="No recent activity — start by creating an agent or running a workflow."
        emptyIcon={Sparkles}
        emptyTitle="No recent activity"
        events={events}
        isLoading={isLoading}
        skeletonCount={5}
      />
    </section>
  );
}
