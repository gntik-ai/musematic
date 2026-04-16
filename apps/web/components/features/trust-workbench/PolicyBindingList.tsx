"use client";

import type { DragEvent } from "react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { PolicyBinding } from "@/lib/types/trust-workbench";
import { PolicyBindingCard } from "@/components/features/trust-workbench/PolicyBindingCard";
import { cn } from "@/lib/utils";

export interface PolicyBindingListProps {
  bindings: PolicyBinding[];
  isLoading: boolean;
  isDragOver: boolean;
  dropError: string | null;
  onDrop: (policyId: string) => void;
  onDragOver: (event: DragEvent<HTMLDivElement>) => void;
  onDragLeave: () => void;
  onRemove: (attachmentId: string, policyId: string) => void;
}

export function PolicyBindingList({
  bindings,
  isLoading,
  isDragOver,
  dropError,
  onDrop,
  onDragOver,
  onDragLeave,
  onRemove,
}: PolicyBindingListProps) {
  return (
    <TooltipProvider>
      <Card
        className={cn(
          "h-full rounded-[1.75rem] border-2 border-dashed transition-colors",
          isDragOver && "border-brand-accent bg-brand-accent/5",
          dropError && "border-destructive bg-destructive/5",
        )}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={(event) => {
          event.preventDefault();
          const policyId = event.dataTransfer.getData("policyId");
          onDrop(policyId);
        }}
      >
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle>Effective bindings</CardTitle>
              <p className="text-sm text-muted-foreground">
                Direct and inherited policy bindings currently affecting this certification.
              </p>
            </div>
            {dropError ? (
              <Tooltip>
                <TooltipTrigger>
                  <span className="rounded-full border border-destructive/30 bg-destructive/10 px-3 py-1 text-xs font-semibold text-foreground">
                    Drop blocked
                  </span>
                </TooltipTrigger>
                <TooltipContent>{dropError}</TooltipContent>
              </Tooltip>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {isLoading
            ? Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-28 rounded-[1.5rem]" />
              ))
            : bindings.length === 0
              ? (
                  <EmptyState
                    description="Drag a policy here to attach it."
                    title="No policies attached"
                  />
                )
              : bindings.map((binding) => (
                  <PolicyBindingCard
                    key={`${binding.attachmentId}-${binding.policyId}`}
                    binding={binding}
                    onRemove={
                      binding.canRemove
                        ? (attachmentId) => onRemove(attachmentId, binding.policyId)
                        : undefined
                    }
                  />
                ))}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
