"use client";

/**
 * UPD-049 refresh (102) — Filter chips for the marketplace review queue.
 *
 * Three chips: "Unassigned" / "Assigned to me" / "All". The chip state
 * maps to the `assigned_to` query parameter on the GET /queue endpoint
 * via the `assignment` field of `ReviewQueueFilter`.
 */

import { Button } from "@/components/ui/button";
import type { QueueAssignmentFilter } from "@/lib/marketplace/types";

export interface ReviewQueueFilterChipsProps {
  value: QueueAssignmentFilter;
  onChange: (value: QueueAssignmentFilter) => void;
}

const CHIPS: Array<{ value: QueueAssignmentFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "unassigned", label: "Unassigned" },
  { value: "me", label: "Assigned to me" },
];

export function ReviewQueueFilterChips({
  value,
  onChange,
}: ReviewQueueFilterChipsProps) {
  return (
    <div
      className="flex flex-wrap items-center gap-2"
      role="group"
      aria-label="Filter review queue by assignment"
      data-testid="review-queue-filter-chips"
    >
      {CHIPS.map((chip) => {
        const active = chip.value === value;
        return (
          <Button
            key={chip.value}
            type="button"
            variant={active ? "default" : "outline"}
            size="sm"
            onClick={() => onChange(chip.value)}
            data-testid={`queue-filter-chip-${chip.value}`}
            aria-pressed={active}
          >
            {chip.label}
          </Button>
        );
      })}
    </div>
  );
}
