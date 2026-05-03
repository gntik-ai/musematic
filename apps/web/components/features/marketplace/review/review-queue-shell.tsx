"use client";

/**
 * UPD-049 — Client shell that wires the TanStack Query hook and the
 * filter UI to ReviewQueueTable. Refresh-pass (102) adds the
 * assignment filter chips (Unassigned / Assigned to me / All).
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useReviewQueue } from "@/lib/hooks/use-marketplace-review";
import { ReviewQueueFilterChips } from "@/components/features/marketplace/review/review-queue-filter-chips";
import { ReviewQueueTable } from "@/components/features/marketplace/review/review-queue-table";
import type { QueueAssignmentFilter } from "@/lib/marketplace/types";

export function ReviewQueueShell() {
  const [unclaimedOnly, setUnclaimedOnly] = useState(false);
  const [assignment, setAssignment] = useState<QueueAssignmentFilter>("all");
  const { data, isLoading, isError, refetch } = useReviewQueue({
    unclaimedOnly,
    assignment,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <ReviewQueueFilterChips value={assignment} onChange={setAssignment} />
        <Button
          variant={unclaimedOnly ? "default" : "outline"}
          size="sm"
          onClick={() => setUnclaimedOnly((prev) => !prev)}
          data-testid="review-queue-unclaimed-toggle"
        >
          {unclaimedOnly ? "Showing unclaimed only" : "Show unclaimed only"}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => void refetch()}>
          Refresh
        </Button>
      </div>
      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : isError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Could not load the review queue. Try refreshing.
        </div>
      ) : (
        <ReviewQueueTable items={data?.items ?? []} />
      )}
    </div>
  );
}
