"use client";

import { formatDistanceToNow } from "date-fns";
import { Timeline, type TimelineEvent } from "@/components/shared/Timeline";
import type {
  CertificationStatus,
  CertificationStatusEvent,
} from "@/lib/types/trust-workbench";
import { CERTIFICATION_STATUS_LABELS } from "@/lib/types/trust-workbench";
import type { StatusSemantic } from "@/components/shared/StatusBadge";

function toTimelineStatus(status: CertificationStatus): StatusSemantic {
  switch (status) {
    case "active":
      return "healthy";
    case "pending":
      return "pending";
    case "expired":
    case "revoked":
      return "error";
    case "superseded":
      return "inactive";
    default:
      return "warning";
  }
}

export interface StatusTimelineProps {
  events: CertificationStatusEvent[];
  currentStatus: CertificationStatus;
  isLoading?: boolean;
}

export function StatusTimeline({
  events,
  currentStatus,
  isLoading = false,
}: StatusTimelineProps) {
  const items = [...events]
    .sort(
      (left, right) =>
        new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime(),
    )
    .map<TimelineEvent>((event) => ({
      id: event.id,
      label:
        event.status === currentStatus
          ? `${CERTIFICATION_STATUS_LABELS[event.status]} (current)`
          : CERTIFICATION_STATUS_LABELS[event.status],
      description: event.notes
        ? `${event.actor}: ${event.notes}`
        : `Updated by ${event.actor}`,
      status: toTimelineStatus(event.status),
      timestamp: event.timestamp,
      timestampLabel: formatDistanceToNow(new Date(event.timestamp), {
        addSuffix: true,
      }),
    }));

  return (
    <Timeline
      emptyDescription="Status changes will appear here once the certification enters review."
      emptyTitle="No review history"
      events={items}
      isLoading={isLoading}
    />
  );
}
