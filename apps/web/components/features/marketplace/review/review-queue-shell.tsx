"use client";

/**
 * UPD-049 — Client shell that wires the TanStack Query hook and the
 * filter UI to ReviewQueueTable.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useReviewQueue } from "@/lib/hooks/use-marketplace-review";
import { ReviewQueueTable } from "@/components/features/marketplace/review/review-queue-table";

export function ReviewQueueShell() {
  const [unclaimedOnly, setUnclaimedOnly] = useState(false);
  const { data, isLoading, isError, refetch } = useReviewQueue({ unclaimedOnly });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
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
