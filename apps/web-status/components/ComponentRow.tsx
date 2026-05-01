import { formatDistanceToNow } from "date-fns";
import Link from "next/link";

import type { ComponentStatus, OverallState } from "@/lib/status-client";

type ComponentRowProps = {
  component: ComponentStatus;
  label: string;
};

const dotClasses: Record<OverallState, string> = {
  operational: "bg-emerald-500",
  degraded: "bg-amber-500",
  partial_outage: "bg-orange-500",
  full_outage: "bg-red-500",
  maintenance: "bg-sky-500",
};

export function ComponentRow({ component, label }: ComponentRowProps) {
  const checkedAt = new Date(component.last_check_at);
  const uptime =
    typeof component.uptime_30d_pct === "number"
      ? `${component.uptime_30d_pct.toFixed(2)}%`
      : "100.00%";

  return (
    <Link
      href={`/components/${component.id}/`}
      className="grid min-h-20 grid-cols-[1fr_auto] gap-4 border-b border-border px-4 py-4 transition hover:bg-muted/70 focus-visible:bg-muted/70 md:grid-cols-[1fr_180px_140px]"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span
          aria-hidden="true"
          className={`h-3 w-3 shrink-0 rounded-full ${dotClasses[component.state]}`}
        />
        <div className="min-w-0">
          <p className="truncate text-base font-medium">{component.name}</p>
          <p className="mt-1 text-sm text-muted-foreground">{label}</p>
        </div>
      </div>
      <p className="hidden self-center text-sm text-muted-foreground md:block">
        {formatDistanceToNow(checkedAt, { addSuffix: true })}
      </p>
      <p className="self-center text-right font-mono text-sm font-semibold">{uptime}</p>
    </Link>
  );
}
