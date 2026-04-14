"use client";

import { formatDistanceToNow } from "date-fns";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useExecutionJournal } from "@/lib/hooks/use-execution-journal";
import { cn } from "@/lib/utils";
import type { ExecutionEvent, ExecutionEventType } from "@/types/execution";

function getEventPresentation(eventType: ExecutionEventType) {
  if (eventType.includes("FAILED") || eventType.includes("REJECTED")) {
    return {
      borderClassName: "border-l-destructive",
      icon: AlertTriangle,
      label: "Failure",
    };
  }

  if (eventType.includes("APPROVAL") || eventType.includes("APPROVED")) {
    return {
      borderClassName: "border-l-amber-500",
      icon: ShieldAlert,
      label: "Approval",
    };
  }

  if (
    eventType.includes("REASONING") ||
    eventType.includes("SELF_CORRECTION") ||
    eventType.includes("BUDGET_THRESHOLD")
  ) {
    return {
      borderClassName: "border-l-violet-500",
      icon: Sparkles,
      label: "Reasoning",
    };
  }

  if (
    eventType.includes("STARTED") ||
    eventType.includes("DISPATCHED") ||
    eventType.includes("RUNNING") ||
    eventType.includes("RESUMED")
  ) {
    return {
      borderClassName: "border-l-brand-primary",
      icon: Loader2,
      label: "Runtime",
    };
  }

  return {
    borderClassName: "border-l-emerald-500",
    icon: CheckCircle2,
    label: "Lifecycle",
  };
}

function TimelineItem({ event }: { event: ExecutionEvent }) {
  const presentation = getEventPresentation(event.eventType);
  const Icon = presentation.icon;

  return (
    <article
      className={cn(
        "rounded-2xl border border-border/70 border-l-4 bg-card/80 p-4",
        presentation.borderClassName,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <Icon
            className={cn(
              "mt-0.5 h-4 w-4",
              event.eventType.includes("STARTED") ? "animate-spin" : "",
            )}
          />
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium text-foreground">{event.eventType}</p>
              <Badge variant="outline">{presentation.label}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {event.stepId ? `Step ${event.stepId}` : "Execution-level event"}
            </p>
          </div>
        </div>
        <p className="shrink-0 text-xs text-muted-foreground">
          {formatDistanceToNow(new Date(event.createdAt), { addSuffix: true })}
        </p>
      </div>
    </article>
  );
}

export function ExecutionTimeline({
  executionId,
}: {
  executionId: string;
}) {
  const journalQuery = useExecutionJournal(executionId, { limit: 20 });
  const events =
    journalQuery.data?.pages
      .flatMap((page) => page.items)
      .slice()
      .reverse() ?? [];

  if (journalQuery.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <EmptyState
        description="No journal events have been recorded for this execution yet."
        icon={Clock3}
        title="Timeline is empty"
      />
    );
  }

  return (
    <section className="space-y-4">
      <div aria-live="polite" className="space-y-3">
        {events.map((event) => (
          <TimelineItem event={event} key={event.id} />
        ))}
      </div>

      {journalQuery.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            disabled={journalQuery.isFetchingNextPage}
            onClick={() => {
              void journalQuery.fetchNextPage();
            }}
            variant="outline"
          >
            {journalQuery.isFetchingNextPage ? "Loading more..." : "Load more events"}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
