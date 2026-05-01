import { formatDistanceToNow } from "date-fns";
import Link from "next/link";

import type { PublicIncident } from "@/lib/status-client";

type IncidentTimelineProps = {
  incidents: PublicIncident[];
  emptyLabel: string;
};

const severityClasses: Record<PublicIncident["severity"], string> = {
  info: "border-sky-200 bg-sky-50 text-sky-800",
  warning: "border-amber-200 bg-amber-50 text-amber-800",
  high: "border-orange-200 bg-orange-50 text-orange-800",
  critical: "border-red-200 bg-red-50 text-red-800",
};

export function IncidentTimeline({ incidents, emptyLabel }: IncidentTimelineProps) {
  if (incidents.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border p-6 text-sm text-muted-foreground">
        {emptyLabel}
      </div>
    );
  }

  const sorted = [...incidents].sort(
    (left, right) => Date.parse(right.last_update_at) - Date.parse(left.last_update_at),
  );

  return (
    <ol className="divide-y divide-border rounded-md border border-border bg-card">
      {sorted.map((incident) => (
        <li key={incident.id} className="p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-2.5 py-1 text-xs font-semibold uppercase tracking-normal ${severityClasses[incident.severity]}`}
            >
              {incident.severity}
            </span>
            <span className="text-sm text-muted-foreground">
              {formatDistanceToNow(new Date(incident.last_update_at), { addSuffix: true })}
            </span>
          </div>
          <Link
            href={`/incidents/${incident.id}/`}
            className="mt-3 block text-base font-semibold hover:underline"
          >
            {incident.title}
          </Link>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {incident.last_update_summary}
          </p>
        </li>
      ))}
    </ol>
  );
}
