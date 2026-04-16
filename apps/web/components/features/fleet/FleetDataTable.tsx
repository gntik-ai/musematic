"use client";

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { formatDistanceToNow } from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FleetStatusBadge } from "@/components/features/fleet/FleetStatusBadge";
import { FleetTopologyBadge } from "@/components/features/fleet/FleetTopologyBadge";
import { DataTable } from "@/components/shared/DataTable";
import { FilterBar, type FilterDefinition } from "@/components/shared/FilterBar";
import { SearchInput } from "@/components/shared/SearchInput";
import { Button } from "@/components/ui/button";
import { useFleets } from "@/lib/hooks/use-fleets";
import { parseFleetListFilters, serializeFleetListFilters } from "@/lib/schemas/fleet";
import {
  DEFAULT_FLEET_LIST_FILTERS,
  FLEET_STATUS_LABELS,
  FLEET_TOPOLOGY_LABELS,
  getFleetHealthTone,
  type FleetListEntry,
  type FleetListFilters,
  type FleetStatus,
  type FleetTopologyType,
} from "@/lib/types/fleet";
import { cn } from "@/lib/utils";

export interface FleetDataTableProps {
  workspace_id: string;
}

function InlineHealthBar({ score }: { score: number }) {
  const tone = getFleetHealthTone(score);
  const indicatorClassName =
    tone === "healthy"
      ? "bg-emerald-500"
      : tone === "warning"
        ? "bg-amber-500"
        : "bg-rose-500";

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
        <span>Health</span>
        <span className="font-medium text-foreground">{score}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-[width]", indicatorClassName)}
          style={{ width: `${Math.max(0, Math.min(score, 100))}%` }}
        />
      </div>
    </div>
  );
}

export function FleetDataTable({ workspace_id }: FleetDataTableProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => parseFleetListFilters(searchParams), [searchParams]);
  const fleetsQuery = useFleets(filters, { workspaceId: workspace_id });

  const filterDefinitions = useMemo<FilterDefinition[]>(
    () => [
      {
        id: "topology_type",
        label: "Topology",
        multiple: true,
        value: filters.topology_type,
        options: (Object.entries(FLEET_TOPOLOGY_LABELS) as [
          FleetTopologyType,
          string,
        ][]).map(([value, label]) => ({
          value,
          label,
        })),
      },
      {
        id: "status",
        label: "Status",
        multiple: true,
        value: filters.status,
        options: (Object.entries(FLEET_STATUS_LABELS) as [FleetStatus, string][]).map(
          ([value, label]) => ({
            value,
            label,
          }),
        ),
      },
      {
        id: "health_min",
        label: "Min health",
        value: filters.health_min ? String(filters.health_min) : "",
        options: [
          { value: "40", label: "40+" },
          { value: "70", label: "70+" },
          { value: "85", label: "85+" },
        ],
      },
    ],
    [filters.health_min, filters.status, filters.topology_type],
  );

  const columns = useMemo<ColumnDef<FleetListEntry>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Fleet",
        cell: ({ row }) => (
          <div className="space-y-1">
            <a
              className="font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              href={`/fleet/${encodeURIComponent(row.original.id)}`}
            >
              {row.original.name}
            </a>
            <p className="text-xs text-muted-foreground">{row.original.id}</p>
          </div>
        ),
      },
      {
        accessorKey: "topology_type",
        header: "Topology",
        cell: ({ row }) => <FleetTopologyBadge topology={row.original.topology_type} />,
      },
      {
        accessorKey: "member_count",
        header: "Members",
        cell: ({ row }) => row.original.member_count,
      },
      {
        accessorKey: "health_pct",
        header: "Health",
        cell: ({ row }) => <InlineHealthBar score={row.original.health_pct} />,
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <FleetStatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "updated_at",
        header: "Updated",
        cell: ({ row }) =>
          formatDistanceToNow(new Date(row.original.updated_at), { addSuffix: true }),
      },
    ],
    [],
  );

  const updateSearchParams = (nextValues: Partial<FleetListFilters>) => {
    const nextQuery = serializeFleetListFilters({
      ...filters,
      ...nextValues,
    }).toString();

    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname);
  };

  const currentPage = fleetsQuery.data?.page ?? filters.page;
  const pageSize = fleetsQuery.data?.size ?? filters.size;
  const total = fleetsQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="w-full max-w-xl">
          <SearchInput
            defaultValue={filters.search}
            isLoading={fleetsQuery.isFetching}
            placeholder="Search fleets"
            onChange={(value) =>
              updateSearchParams({
                ...DEFAULT_FLEET_LIST_FILTERS,
                ...filters,
                search: value,
                page: 1,
              })
            }
          />
        </div>
        <p className="text-sm text-muted-foreground">{total} fleets in view</p>
      </div>

      <FilterBar
        filters={filterDefinitions}
        onChange={(id, value) => {
          if (id === "health_min") {
            updateSearchParams({
              ...filters,
              health_min: Array.isArray(value) || value === "" ? null : Number(value),
              page: 1,
            });
            return;
          }

          updateSearchParams({
            ...filters,
            [id]: Array.isArray(value) ? value : value ? [value] : [],
            page: 1,
          } as Partial<FleetListFilters>);
        }}
        onClear={() => updateSearchParams({ ...DEFAULT_FLEET_LIST_FILTERS })}
      />

      <DataTable
        columns={columns}
        data={fleetsQuery.data?.items ?? []}
        enableFiltering={false}
        emptyStateMessage="No fleets match the active filters."
        hidePagination
        isLoading={fleetsQuery.isLoading}
      />

      <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-card/70 p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Page {currentPage} of {totalPages}
        </p>
        <div className="flex items-center gap-2">
          <Button
            disabled={currentPage <= 1}
            size="sm"
            variant="outline"
            onClick={() => updateSearchParams({ ...filters, page: Math.max(1, currentPage - 1) })}
          >
            <ChevronLeft className="h-4 w-4" />
            Previous
          </Button>
          <Button
            disabled={currentPage >= totalPages}
            size="sm"
            variant="outline"
            onClick={() =>
              updateSearchParams({
                ...filters,
                page: Math.min(totalPages, currentPage + 1),
              })
            }
          >
            Next
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
