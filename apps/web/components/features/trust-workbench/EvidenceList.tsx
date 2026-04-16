"use client";

import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import type { EvidenceItem } from "@/lib/types/trust-workbench";
import { EvidenceItemCard } from "@/components/features/trust-workbench/EvidenceItemCard";

export interface EvidenceListProps {
  items: EvidenceItem[];
  isLoading?: boolean;
}

export function EvidenceList({
  items,
  isLoading = false,
}: EvidenceListProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-[1.5rem]" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        description="Automated evidence collection may still be in progress."
        title="No evidence collected yet"
      />
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item) => (
        <EvidenceItemCard key={item.id} item={item} />
      ))}
    </div>
  );
}
