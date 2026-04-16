"use client";

import { Badge } from "@/components/ui/badge";
import { cn, toTitleCase } from "@/lib/utils";
import type { AgentStatus } from "@/lib/types/agent-management";

const STATUS_STYLES: Record<AgentStatus, string> = {
  draft: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  active: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  archived: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300",
  pending_review: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
};

export interface AgentStatusBadgeProps {
  status: AgentStatus;
}

export function AgentStatusBadge({ status }: AgentStatusBadgeProps) {
  return (
    <Badge
      aria-label={`Lifecycle state ${toTitleCase(status)}`}
      className={cn("border-0 px-2.5 py-1 text-sm", STATUS_STYLES[status])}
      role="status"
      variant="outline"
    >
      {toTitleCase(status)}
    </Badge>
  );
}
