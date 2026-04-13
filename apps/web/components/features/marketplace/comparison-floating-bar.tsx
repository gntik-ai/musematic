"use client";

import { GitCompareArrows, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ComparisonFloatingBarProps {
  selectedFqns: string[];
  onClear: () => void;
  onCompare: () => void;
}

export function ComparisonFloatingBar({
  selectedFqns,
  onClear,
  onCompare,
}: ComparisonFloatingBarProps) {
  if (selectedFqns.length < 1) {
    return null;
  }

  return (
    <div
      aria-live="polite"
      className="fixed inset-x-4 bottom-4 z-40 mx-auto flex max-w-3xl items-center justify-between gap-4 rounded-2xl border border-border/70 bg-background/95 px-4 py-3 shadow-2xl backdrop-blur"
      role="status"
    >
      <div className="min-w-0">
        <p className="text-sm font-semibold">
          {selectedFqns.length} {selectedFqns.length === 1 ? "agent" : "agents"} selected
        </p>
        <p className="text-sm text-muted-foreground">
          Compare up to four agents side by side before invoking one.
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button size="sm" variant="ghost" onClick={onClear}>
          <X className="h-4 w-4" />
          Clear
        </Button>
        <Button
          size="sm"
          disabled={selectedFqns.length < 2}
          onClick={onCompare}
        >
          <GitCompareArrows className="h-4 w-4" />
          Compare now
        </Button>
      </div>
    </div>
  );
}
