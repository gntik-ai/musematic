"use client";

import * as React from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type PaginationState,
  type SortingState,
} from "@tanstack/react-table";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export interface DataTableProps<TData> {
  columns: ColumnDef<TData>[];
  data: TData[];
  isLoading?: boolean;
  emptyStateMessage?: string;
  emptyStateCta?: React.ReactNode;
  pageSize?: number;
  enableSorting?: boolean;
  enableFiltering?: boolean;
  hidePagination?: boolean;
  onRowClick?: ((row: TData) => void) | undefined;
  onPaginationChange?: ((state: PaginationState) => void) | undefined;
  onSortingChange?: ((state: SortingState) => void) | undefined;
  onFilterChange?: ((state: ColumnFiltersState) => void) | undefined;
  totalCount?: number | undefined;
}

export function DataTable<TData>({
  columns,
  data,
  emptyStateMessage = "No data available.",
  enableFiltering = true,
  enableSorting = true,
  hidePagination = false,
  isLoading = false,
  onRowClick,
  onFilterChange,
  onPaginationChange,
  onSortingChange,
  pageSize = 10,
  totalCount,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [pagination, setPagination] = React.useState<PaginationState>({ pageIndex: 0, pageSize });

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnFilters,
      pagination,
    },
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    ...(totalCount === undefined ? { getPaginationRowModel: getPaginationRowModel() } : {}),
    manualPagination: totalCount !== undefined,
    onSortingChange: (updater) => {
      const next = typeof updater === "function" ? updater(sorting) : updater;
      setSorting(next);
      onSortingChange?.(next);
    },
    onColumnFiltersChange: (updater) => {
      const next = typeof updater === "function" ? updater(columnFilters) : updater;
      setColumnFilters(next);
      onFilterChange?.(next);
    },
    onPaginationChange: (updater) => {
      const next = typeof updater === "function" ? updater(pagination) : updater;
      setPagination(next);
      onPaginationChange?.(next);
    },
  });

  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card/80 p-4" aria-busy={isLoading}>
      {enableFiltering ? (
        <Input
          aria-label="Filter rows"
          placeholder="Filter rows"
          value={(table.getColumn(columns[0]?.id ?? "")?.getFilterValue() as string | undefined) ?? ""}
          onChange={(event) => {
            const column = columns[0]?.id ? table.getColumn(columns[0].id) : undefined;
            column?.setFilterValue(event.target.value);
          }}
        />
      ) : null}
      <div className="overflow-hidden rounded-xl border border-border/70">
        <Table>
          <TableCaption>Operational data table</TableCaption>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const canSort = enableSorting && header.column.getCanSort();
                  const sortState = header.column.getIsSorted();

                  return (
                    <TableHead key={header.id} aria-sort={sortState === "asc" ? "ascending" : sortState === "desc" ? "descending" : "none"}>
                      {header.isPlaceholder ? null : canSort ? (
                        <button className="inline-flex items-center gap-2 font-semibold" onClick={header.column.getToggleSortingHandler()} type="button">
                          {flexRender(header.column.columnDef.header, header.getContext())}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, index) => (
                  <TableRow key={`skeleton-${index}`}>
                    {columns.map((column, columnIndex) => (
                      <TableCell key={`${String(column.id ?? columnIndex)}-${index}`}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : table.getRowModel().rows.map((row) => (
                  <TableRow key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell
                        key={cell.id}
                        className={onRowClick ? "cursor-pointer" : undefined}
                        onClick={() => onRowClick?.(row.original)}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
      {!isLoading && table.getRowModel().rows.length === 0 ? (
        <EmptyState description={emptyStateMessage} title="No rows found" />
      ) : null}
      {!hidePagination ? (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {totalCount ? `${totalCount} total rows` : `${table.getRowModel().rows.length} visible rows`}
          </p>
          <div className="flex items-center gap-2">
            <Button
              disabled={!table.getCanPreviousPage()}
              size="icon"
              variant="outline"
              onClick={() => table.previousPage()}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              disabled={!table.getCanNextPage()}
              size="icon"
              variant="outline"
              onClick={() => table.nextPage()}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
