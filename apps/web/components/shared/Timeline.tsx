"use client";

import { format } from "date-fns";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge, type StatusSemantic } from "@/components/shared/StatusBadge";
import { Skeleton } from "@/components/ui/skeleton";

export interface TimelineEvent {
  id: string;
  timestamp: string;
  label: string;
  description?: string | undefined;
  status?: StatusSemantic | undefined;
  href?: string | undefined;
  timestampLabel?: string | undefined;
}

export function Timeline({
  emptyDescription = "Events will appear here once activity starts streaming.",
  emptyIcon,
  emptyTitle = "No timeline activity",
  events,
  isLoading = false,
  skeletonCount = 4,
}: {
  events: TimelineEvent[];
  isLoading?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
    emptyIcon?: LucideIcon | undefined;
  skeletonCount?: number;
}) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: skeletonCount }).map((_, index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <EmptyState
        description={emptyDescription}
        icon={emptyIcon}
        title={emptyTitle}
      />
    );
  }

  return (
    <div className="space-y-4">
      {events.map((event) => (
        <article
          key={event.id}
          className="relative rounded-xl border border-border bg-card/80 p-4"
        >
          {event.href ? (
            <Link className="absolute inset-0 rounded-xl" href={event.href}>
              <span className="sr-only">{event.label}</span>
            </Link>
          ) : null}
          <div className="relative">
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <span
                className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground"
              >
                {event.timestampLabel ?? format(new Date(event.timestamp), "PPp")}
              </span>
              {event.status ? <StatusBadge status={event.status} /> : null}
            </div>
            <p className="font-medium">{event.label}</p>
            {event.description ? (
              <p className="mt-2 text-sm text-muted-foreground">
                {event.description}
              </p>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}
