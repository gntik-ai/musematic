"use client";

import { format, parseISO } from "date-fns";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { EvaluationRunResponse } from "@/types/evaluation";

export interface EvalRunListProps {
  runs: EvaluationRunResponse[];
  evalSetId: string;
  onRunSelect: (runId: string) => void;
  selectedRunId?: string | undefined;
  selectedRunIds?: Set<string> | undefined;
  onSelectionChange?: ((ids: Set<string>) => void) | undefined;
  onCompare?: ((runIds: [string, string]) => void) | undefined;
  isLoading?: boolean | undefined;
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "—";
  }

  const date = parseISO(value);
  return Number.isNaN(date.getTime()) ? "—" : format(date, "MMM d, yyyy HH:mm");
}

function toggleSelection(
  selected: Set<string> | undefined,
  runId: string,
  onSelectionChange?: (ids: Set<string>) => void,
) {
  if (!onSelectionChange) {
    return;
  }

  const next = new Set(selected ?? []);
  if (next.has(runId)) {
    next.delete(runId);
  } else {
    if (next.size >= 2) {
      const [first] = next;
      if (first) {
        next.delete(first);
      }
    }
    next.add(runId);
  }

  onSelectionChange(next);
}

export function EvalRunList({
  runs,
  onCompare,
  onRunSelect,
  selectedRunId,
  selectedRunIds,
  onSelectionChange,
  isLoading = false,
}: EvalRunListProps) {
  const selectedIds = selectedRunIds ?? new Set<string>();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="h-24 animate-pulse rounded-2xl border border-border/70 bg-muted/20"
          />
        ))}
      </div>
    );
  }

  return (
    <section className="space-y-4">
      {selectedIds.size === 2 && onCompare ? (
        <div className="flex justify-end">
          <Button
            onClick={() => {
              const [runA, runB] = Array.from(selectedIds);
              if (runA && runB) {
                onCompare([runA, runB]);
              }
            }}
            variant="secondary"
          >
            Compare
          </Button>
        </div>
      ) : null}
      <div className="space-y-3">
        {runs.map((run) => {
          const selected = run.id === selectedRunId;
          const checked = selectedIds.has(run.id);
          return (
            <div
              key={run.id}
              aria-selected={selected}
              className={`rounded-2xl border p-4 transition-colors ${selected ? "border-primary bg-primary/5" : "border-border/70 bg-card/80 hover:bg-muted/30"}`}
              role="button"
              tabIndex={0}
              onClick={() => onRunSelect(run.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  onRunSelect(run.id);
                }
                if (event.key === " ") {
                  event.preventDefault();
                  toggleSelection(selectedIds, run.id, onSelectionChange);
                }
              }}
            >
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div className="flex items-start gap-3">
                  {onSelectionChange ? (
                    <Checkbox
                      aria-label={`Select run ${run.id} for comparison`}
                      checked={checked}
                      onChange={() =>
                        toggleSelection(selectedIds, run.id, onSelectionChange)
                      }
                      onClick={(event) => event.stopPropagation()}
                    />
                  ) : null}
                  <div className="space-y-2">
                    <p className="font-medium">Run {run.id.slice(0, 8)}</p>
                    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                      <span>{formatDateTime(run.started_at)}</span>
                      <span>•</span>
                      <span>{run.total_cases} cases</span>
                      <span>•</span>
                      <span>{run.passed_cases} passed</span>
                      <span>•</span>
                      <span>{run.failed_cases} failed</span>
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <StatusBadge
                    label={run.status}
                    status={
                      run.status === "completed"
                        ? "healthy"
                        : run.status === "failed"
                          ? "error"
                          : run.status === "running"
                            ? "running"
                            : "pending"
                    }
                  />
                  <span className="text-sm font-medium">
                    {typeof run.aggregate_score === "number"
                      ? `${Math.round(run.aggregate_score * 100)}%`
                      : "—"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
