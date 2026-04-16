"use client";

import { Badge } from "@/components/ui/badge";
import { cn, toTitleCase } from "@/lib/utils";
import type { AgentMaturity } from "@/lib/types/agent-management";

const MATURITY_STYLES: Record<AgentMaturity, string> = {
  experimental: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
  beta: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  production: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  deprecated: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
};

export interface AgentMaturityBadgeProps {
  maturity: AgentMaturity;
  size?: "sm" | "md";
}

export function AgentMaturityBadge({
  maturity,
  size = "md",
}: AgentMaturityBadgeProps) {
  return (
    <Badge
      aria-label={`Release stage ${toTitleCase(maturity)}`}
      className={cn(
        "border-0",
        MATURITY_STYLES[maturity],
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
      )}
      role="status"
      variant="outline"
    >
      {toTitleCase(maturity)}
    </Badge>
  );
}
