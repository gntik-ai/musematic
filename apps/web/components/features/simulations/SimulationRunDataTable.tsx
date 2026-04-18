"use client";

import { format, parseISO } from "date-fns";
import { type ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { SimulationRunResponse } from "@/types/simulation";

export interface SimulationRunDataTableProps {
  runs: SimulationRunResponse[];
  isLoading?: boolean | undefined;
  nextCursor: string | null;
  selectedRunIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
  onRowClick: (runId: string) => void;
  onLoadMore: () => void;
  onCreate: () => void;
  onCompare: (runIds: [string, string]) => void;
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "—";
  }

  const date = parseISO(value);
  return Number.isNaN(date.getTime()) ? "—" : format(date, "MMM d, yyyy HH:mm");
}

function statusClasses(status: SimulationRunResponse["status"]): string {
  switch (status) {
    case "completed":
      return "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300";
    case "failed":
    case "timeout":
      return "bg-destructive/10 text-foreground";
    case "cancelled":
      return "text-muted-foreground";
    case "running":
      return "bg-sky-500/15 text-sky-700 dark:text-sky-300";
    case "provisioning":
    default:
      return "bg-amber-500/15 text-amber-700 dark:text-amber-300";
  }
}

function toggleSelection(
  selectedRunIds: Set<string>,
  runId: string,
  onSelectionChange: (ids: Set<string>) => void,
) {
  const next = new Set(selectedRunIds);
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

export function SimulationRunDataTable({
  runs,
  isLoading = false,
  nextCursor,
  selectedRunIds,
  onSelectionChange,
  onRowClick,
  onLoadMore,
  onCreate,
  onCompare,
}: SimulationRunDataTableProps) {
  if (!isLoading && runs.length === 0) {
    return (
      <EmptyState
        ctaLabel="Create Simulation"
        description="Launch your first simulation to compare digital twins and production behavior."
        title="No simulations yet"
        onCtaClick={onCreate}
      />
    );
  }

  const columns: ColumnDef<SimulationRunResponse>[] = [
    {
      id: "selection",
      header: "",
      cell: ({ row }) => (
        <Checkbox
          aria-label={`Select simulation ${row.original.name} for comparison`}
          checked={selectedRunIds.has(row.original.run_id)}
          onChange={() =>
            toggleSelection(selectedRunIds, row.original.run_id, onSelectionChange)
          }
          onClick={(event) => event.stopPropagation()}
        />
      ),
    },
    {
      accessorKey: "name",
      header: "Name",
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <Badge className={statusClasses(row.original.status)} variant="secondary">
          {row.original.status}
        </Badge>
      ),
    },
    {
      id: "twins",
      header: "Digital Twin(s)",
      cell: ({ row }) =>
        row.original.digital_twin_ids.length === 1
          ? row.original.digital_twin_ids[0]
          : `${row.original.digital_twin_ids.length} twins`,
    },
    {
      id: "completedAt",
      header: "Completion Date",
      cell: ({ row }) => formatDateTime(row.original.completed_at),
    },
  ];

  return (
    <section className="space-y-4">
      <div className="flex justify-between gap-3">
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4" />
          Create Simulation
        </Button>
        <Button
          disabled={selectedRunIds.size !== 2}
          variant="secondary"
          onClick={() => {
            const [primary, secondary] = Array.from(selectedRunIds);
            if (primary && secondary) {
              onCompare([primary, secondary]);
            }
          }}
        >
          Compare
        </Button>
      </div>

      <div className="overflow-x-auto">
        <DataTable
          columns={columns}
          data={runs}
          emptyStateMessage="No simulations found."
          enableFiltering={false}
          hidePagination
          isLoading={isLoading}
          onRowClick={(row) => onRowClick(row.run_id)}
        />
      </div>

      {nextCursor ? (
        <div className="flex justify-end">
          <Button variant="outline" onClick={onLoadMore}>
            Load More
          </Button>
        </div>
      ) : null}
    </section>
  );
}
