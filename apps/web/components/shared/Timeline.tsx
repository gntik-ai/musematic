"use client";

import { format } from "date-fns";
import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge, type StatusSemantic } from "@/components/shared/StatusBadge";
import { Skeleton } from "@/components/ui/skeleton";

export interface TimelineEvent {
  id: string;
  timestamp: string;
  label: string;
  description?: string;
  status?: StatusSemantic;
}

export function Timeline({
  events,
  isLoading = false,
}: {
  events: TimelineEvent[];
  isLoading?: boolean;
}) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return <EmptyState description="Events will appear here once activity starts streaming." title="No timeline activity" />;
  }

  return (
    <div className="space-y-4">
      {events.map((event) => (
        <div key={event.id} className="relative rounded-xl border border-border bg-card/80 p-4">
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              {format(new Date(event.timestamp), "PPp")}
            </span>
            {event.status ? <StatusBadge status={event.status} /> : null}
          </div>
          <p className="font-medium">{event.label}</p>
          {event.description ? <p className="mt-2 text-sm text-muted-foreground">{event.description}</p> : null}
        </div>
      ))}
    </div>
  );
}
