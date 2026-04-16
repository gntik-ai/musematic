"use client";

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { format } from "date-fns";
import { ArrowDownAZ, ArrowDownUp, CalendarClock, ChevronLeft, ChevronRight } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { SearchInput } from "@/components/shared/SearchInput";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  CERTIFICATION_QUEUE_STATUS_LABELS,
  DEFAULT_CERTIFICATION_QUEUE_FILTERS,
  TRUST_WORKBENCH_PAGE_SIZES,
  type CertificationListEntry,
  type CertificationQueueFilters,
} from "@/lib/types/trust-workbench";
import { CertificationStatusBadge } from "@/components/features/trust-workbench/CertificationStatusBadge";

export interface CertificationDataTableProps {
  data: CertificationListEntry[];
  totalCount: number;
  filters: CertificationQueueFilters;
  isLoading: boolean;
  onFiltersChange: (filters: Partial<CertificationQueueFilters>) => void;
  onRowClick: (certificationId: string) => void;
}

function isExpiring(entry: CertificationListEntry): boolean {
  if (entry.status !== "active" || !entry.expiresAt) {
    return false;
  }

  const expiresAt = new Date(entry.expiresAt).getTime();
  const now = Date.now();
  const msRemaining = expiresAt - now;

  return msRemaining >= 0 && msRemaining <= 30 * 24 * 60 * 60 * 1000;
}

function SortButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      className="inline-flex items-center gap-2 font-semibold"
      type="button"
      onClick={onClick}
    >
      {children}
      {active ? <ArrowDownAZ className="h-4 w-4" /> : <ArrowDownUp className="h-4 w-4 text-muted-foreground" />}
    </button>
  );
}

export function CertificationDataTable({
  data,
  totalCount,
  filters,
  isLoading,
  onFiltersChange,
  onRowClick,
}: CertificationDataTableProps) {
  const columns = useMemo<ColumnDef<CertificationListEntry>[]>(
    () => [
      {
        accessorKey: "entityName",
        header: "Entity",
        cell: ({ row }) => (
          <a
            className="block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            href={`/trust-workbench/${encodeURIComponent(row.original.id)}`}
          >
            <div className="space-y-1">
              <p className="font-medium">{row.original.entityName}</p>
              <p className="text-xs text-muted-foreground">{row.original.entityFqn}</p>
            </div>
          </a>
        ),
      },
      {
        accessorKey: "certificationType",
        header: "Certification",
        cell: ({ row }) => (
          <span className="text-sm font-medium">{row.original.certificationType}</span>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: ({ row }) => (
          <CertificationStatusBadge
            expiresAt={row.original.expiresAt}
            size="sm"
            status={isExpiring(row.original) ? "expiring" : row.original.status}
          />
        ),
      },
      {
        accessorKey: "expiresAt",
        header: () => (
          <SortButton
            active={filters.sort_by === "expiration"}
            onClick={() => onFiltersChange({ sort_by: "expiration", page: 1 })}
          >
            Expiration
          </SortButton>
        ),
        cell: ({ row }) =>
          row.original.expiresAt ? (
            <div className="inline-flex items-center gap-2 text-sm">
              <CalendarClock className="h-4 w-4 text-muted-foreground" />
              {format(new Date(row.original.expiresAt), "MMM d, yyyy")}
            </div>
          ) : (
            <span className="text-sm text-muted-foreground">No expiry</span>
          ),
      },
      {
        accessorKey: "evidenceCount",
        header: () => (
          <SortButton
            active={filters.sort_by === "urgency"}
            onClick={() => onFiltersChange({ sort_by: "urgency", page: 1 })}
          >
            Evidence
          </SortButton>
        ),
        cell: ({ row }) => row.original.evidenceCount,
      },
    ],
    [filters.sort_by, onFiltersChange],
  );

  const totalPages = Math.max(1, Math.ceil(totalCount / filters.page_size));

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="w-full max-w-xl">
          <SearchInput
            key={filters.search}
            defaultValue={filters.search}
            isLoading={isLoading}
            placeholder="Search certifications"
            onChange={(value) =>
              onFiltersChange({
                ...DEFAULT_CERTIFICATION_QUEUE_FILTERS,
                ...filters,
                search: value,
                page: 1,
              })
            }
          />
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>Sort</span>
            <Select
              aria-label="Sort certifications"
              value={filters.sort_by}
              onChange={(event) =>
                onFiltersChange({
                  sort_by: event.target.value as CertificationQueueFilters["sort_by"],
                  page: 1,
                })
              }
            >
              <option value="expiration">Expiration</option>
              <option value="urgency">Urgency</option>
              <option value="created">Created</option>
            </Select>
          </label>
          <p className="text-sm text-muted-foreground">{totalCount} certifications in view</p>
        </div>
      </div>

      <Tabs>
        <TabsList className="flex w-full flex-wrap gap-2 rounded-[1.5rem] bg-muted/60 p-2">
          {(["all", "pending", "expiring", "revoked"] as const).map((status) => {
            const isActive =
              status === "all" ? filters.status === null : filters.status === status;

            return (
              <TabsTrigger
                key={status}
                aria-pressed={isActive}
                className={isActive ? "bg-background shadow-sm" : undefined}
                onClick={() =>
                  onFiltersChange({
                    status: status === "all" ? null : status,
                    page: 1,
                  })
                }
              >
                {CERTIFICATION_QUEUE_STATUS_LABELS[status]}
              </TabsTrigger>
            );
          })}
        </TabsList>
      </Tabs>

      <DataTable
        columns={columns}
        data={data}
        enableFiltering={false}
        enableSorting={false}
        emptyStateMessage="No certifications match the active filters."
        getRowAriaLabel={(row) => `Open certification ${row.entityName}`}
        hidePagination
        isLoading={isLoading}
        onRowClick={(row) => onRowClick(row.id)}
      />

      <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-card/70 p-4 md:flex-row md:items-center md:justify-between">
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>Page size</span>
          <Select
            aria-label="Page size"
            value={String(filters.page_size)}
            onChange={(event) =>
              onFiltersChange({
                page: 1,
                page_size: Number(event.target.value) as CertificationQueueFilters["page_size"],
              })
            }
          >
            {TRUST_WORKBENCH_PAGE_SIZES.map((pageSize) => (
              <option key={pageSize} value={pageSize}>
                {pageSize}
              </option>
            ))}
          </Select>
        </label>

        <p className="text-sm text-muted-foreground">
          Page {filters.page} of {totalPages}
        </p>

        <div className="flex items-center gap-2">
          <Button
            disabled={filters.page <= 1}
            size="sm"
            variant="outline"
            onClick={() => onFiltersChange({ page: Math.max(1, filters.page - 1) })}
          >
            <ChevronLeft className="h-4 w-4" />
            Previous
          </Button>
          <Button
            disabled={filters.page >= totalPages}
            size="sm"
            variant="outline"
            onClick={() =>
              onFiltersChange({ page: Math.min(totalPages, filters.page + 1) })
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
