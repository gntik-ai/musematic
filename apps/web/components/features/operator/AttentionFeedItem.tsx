"use client";

import { formatDistanceToNow } from "date-fns";
import { Badge } from "@/components/ui/badge";
import {
  ATTENTION_URGENCY_LABELS,
  type AttentionEvent,
  type AttentionUrgency,
} from "@/lib/types/operator-dashboard";
import { cn } from "@/lib/utils";

export interface AttentionFeedItemProps {
  event: AttentionEvent;
  onClick: (event: AttentionEvent) => void;
}

const urgencyTone: Record<AttentionUrgency, string> = {
  low: "border-slate-400/30 bg-slate-400/12 text-slate-700 dark:text-slate-300",
  medium: "border-blue-500/30 bg-blue-500/12 text-blue-700 dark:text-blue-300",
  high:
    "border-orange-500/30 bg-orange-500/12 text-orange-700 dark:text-orange-300",
  critical: "border-destructive/30 bg-destructive/10 text-foreground",
};

export function AttentionFeedItem({ event, onClick }: AttentionFeedItemProps) {
  return (
    <button
      className={cn(
        "w-full rounded-xl border border-border/60 bg-background/70 px-4 py-3 text-left transition-colors hover:bg-muted/30",
        event.urgency === "critical" && "border-l-4 border-l-destructive font-semibold",
      )}
      type="button"
      onClick={() => onClick(event)}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge className={urgencyTone[event.urgency]} variant="outline">
          {ATTENTION_URGENCY_LABELS[event.urgency]}
        </Badge>
        <span className="text-sm font-medium">{event.sourceAgentFqn}</span>
        <span className="text-xs text-muted-foreground">
          {formatDistanceToNow(new Date(event.createdAt), { addSuffix: true })}
        </span>
      </div>
      <p className="mt-2 text-sm text-foreground">{event.contextSummary}</p>
    </button>
  );
}
