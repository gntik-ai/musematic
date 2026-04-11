"use client";

import { useMemo } from "react";
import { CheckCircle } from "lucide-react";
import { PendingActionCard } from "@/components/features/home/PendingActionCard";
import { SectionError } from "@/components/features/home/SectionError";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePendingActions } from "@/lib/hooks/use-home-data";
import type { PendingAction } from "@/lib/types/home";

interface PendingActionsProps {
  workspaceId: string;
  isConnected?: boolean;
}

const urgencyOrder = {
  high: 0,
  medium: 1,
  low: 2,
} as const;

export function PendingActions({
  workspaceId,
  isConnected,
}: PendingActionsProps) {
  const { data, error, isError, isLoading, refetch } = usePendingActions(
    workspaceId,
    { isConnected },
  );

  const items = useMemo<PendingAction[]>(() => {
    return [...(data?.items ?? [])].sort((left, right) => {
      const urgencyDiff =
        urgencyOrder[left.urgency] - urgencyOrder[right.urgency];
      if (urgencyDiff !== 0) {
        return urgencyDiff;
      }

      return (
        new Date(right.created_at).getTime() -
        new Date(left.created_at).getTime()
      );
    });
  }, [data?.items]);

  if (isError) {
    return (
      <SectionError
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => {
          void refetch();
        }}
        title="Pending actions unavailable"
      />
    );
  }

  if (isLoading) {
    return (
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Pending actions</h2>
          <p className="text-sm text-muted-foreground">
            Approvals, failures, and requests that need attention.
          </p>
        </div>
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, index) => (
            <Card key={index} className="space-y-4 p-6">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-1/2" />
              <div className="flex gap-2">
                <Skeleton className="h-9 w-24" />
                <Skeleton className="h-9 w-24" />
              </div>
            </Card>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Pending actions</h2>
        <p className="text-sm text-muted-foreground">
          Approvals, failures, and requests that need attention.
        </p>
      </div>
      {items.length === 0 ? (
        <EmptyState
          description="All clear — no pending actions"
          icon={CheckCircle}
          title="All clear"
        />
      ) : (
        <div className="space-y-4">
          {items.map((item) => (
            <PendingActionCard
              key={item.id}
              action={item}
              workspaceId={workspaceId}
            />
          ))}
        </div>
      )}
    </section>
  );
}
