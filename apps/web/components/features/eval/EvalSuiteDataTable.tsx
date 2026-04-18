"use client";

import { format, parseISO } from "date-fns";
import Link from "next/link";
import { type ColumnDef } from "@tanstack/react-table";
import { Plus } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import type {
  EvalListFilters,
  EvalSetResponse,
  EvaluationRunResponse,
} from "@/types/evaluation";

interface EvalSuiteRow extends EvalSetResponse {
  last_run?: Partial<EvaluationRunResponse> | null;
}

export interface EvalSuiteDataTableProps {
  data: EvalSetResponse[];
  filters: EvalListFilters;
  isLoading?: boolean | undefined;
  totalCount: number;
  onFiltersChange: (nextValues: Partial<EvalListFilters>) => void;
  onRowClick: (evalSetId: string) => void;
  onCreate: () => void;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

  const date = parseISO(value);
  return Number.isNaN(date.getTime()) ? "—" : format(date, "MMM d, yyyy HH:mm");
}

function formatScore(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

const columns: ColumnDef<EvalSuiteRow>[] = [
  {
    accessorKey: "name",
    header: "Name",
    cell: ({ row }) => (
      <Link
        className="font-medium text-foreground underline-offset-4 hover:underline"
        href={`/evaluation-testing/${encodeURIComponent(row.original.id)}`}
        onClick={(event) => event.stopPropagation()}
      >
        {row.original.name}
      </Link>
    ),
  },
  {
    id: "agent",
    header: "Target Agent",
    cell: ({ row }) => row.original.last_run?.agent_fqn ?? "—",
  },
  {
    id: "lastRunDate",
    header: "Last Run Date",
    cell: ({ row }) =>
      formatDateTime(
        row.original.last_run?.completed_at ??
          row.original.last_run?.started_at ??
          null,
      ),
  },
  {
    id: "lastScore",
    header: "Last Score",
    cell: ({ row }) => formatScore(row.original.last_run?.aggregate_score),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        label={row.original.status === "active" ? "Active" : "Archived"}
        showIcon={false}
        status={row.original.status === "active" ? "healthy" : "inactive"}
      />
    ),
  },
];

export function EvalSuiteDataTable({
  data,
  filters,
  isLoading = false,
  totalCount,
  onCreate,
  onFiltersChange,
  onRowClick,
}: EvalSuiteDataTableProps) {
  if (!isLoading && data.length === 0) {
    return (
      <EmptyState
        ctaLabel="Create Eval Suite"
        description="Create your first eval suite to track benchmark coverage and agent quality."
        title="No eval suites yet"
        onCtaClick={onCreate}
      />
    );
  }

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row">
          <Input
            aria-label="Search eval suites"
            className="sm:max-w-sm"
            placeholder="Search eval suites"
            value={filters.search}
            onChange={(event) =>
              onFiltersChange({ page: 1, search: event.target.value })
            }
          />
          <Select
            aria-label="Filter eval suites by status"
            className="sm:max-w-48"
            value={filters.status}
            onChange={(event) =>
              onFiltersChange({
                page: 1,
                status: event.target.value as EvalListFilters["status"],
              })
            }
          >
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </Select>
        </div>
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4" />
          Create Eval Suite
        </Button>
      </div>

      <div className="overflow-x-auto">
        <DataTable
          columns={columns}
          data={data as EvalSuiteRow[]}
          enableFiltering={false}
          getRowAriaLabel={(row) => `Eval suite ${row.name}`}
          isLoading={isLoading}
          onPaginationChange={(pagination) =>
            onFiltersChange({ page: pagination.pageIndex + 1 })
          }
          onRowClick={(row) => onRowClick(row.id)}
          totalCount={totalCount}
        />
      </div>
    </section>
  );
}
