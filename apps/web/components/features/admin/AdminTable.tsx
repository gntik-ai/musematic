"use client";

import { useEffect, useMemo, useState } from "react";
import type * as React from "react";
import { ChevronLeft, ChevronRight, Download, EyeOff, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { BulkActionBar } from "@/components/features/admin/BulkActionBar";

export interface AdminTableColumn<T> {
  key: keyof T & string;
  label: string;
  render?: (row: T) => React.ReactNode;
  filterable?: boolean;
  sortable?: boolean;
}

interface AdminTableProps<T extends { id: string }> {
  columns: AdminTableColumn<T>[];
  rows: T[];
  pageSize?: number;
  totalRows?: number;
  selectedIds?: string[];
  savedViewsKey?: string;
  onSelectedIdsChange?: (ids: string[]) => void;
  onBulkSuspend?: (ids: string[]) => void;
}

const MAX_PAGE_SIZE = 500;

function cellValue<T extends { id: string }>(row: T, key: keyof T & string): string {
  const value = row[key];
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

export function AdminTable<T extends { id: string }>({
  columns,
  rows,
  pageSize = 50,
  totalRows,
  selectedIds = [],
  savedViewsKey = "default",
  onSelectedIdsChange,
  onBulkSuspend,
}: AdminTableProps<T>) {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sortKey, setSortKey] = useState<keyof T & string>(columns[0]?.key ?? "id");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [pageIndex, setPageIndex] = useState(0);
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(
    () => new Set(columns.map((column) => column.key)),
  );
  const [filters, setFilters] = useState<Record<string, string>>({});
  const safePageSize = Math.min(Math.max(1, pageSize), MAX_PAGE_SIZE);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const visibleColumnList = useMemo(
    () => columns.filter((column) => visibleColumns.has(column.key)),
    [columns, visibleColumns],
  );

  const filteredRows = useMemo(() => {
    const normalizedSearch = debouncedSearch.trim().toLowerCase();
    return rows.filter((row) => {
      const matchesSearch =
        normalizedSearch.length === 0 ||
        columns.some((column) =>
          cellValue(row, column.key).toLowerCase().includes(normalizedSearch),
        );
      if (!matchesSearch) {
        return false;
      }

      return Object.entries(filters).every(([key, value]) => {
        const normalized = value.trim().toLowerCase();
        if (!normalized) {
          return true;
        }
        return cellValue(row, key as keyof T & string).toLowerCase().includes(normalized);
      });
    });
  }, [columns, debouncedSearch, filters, rows]);

  const sortedRows = useMemo(() => {
    return [...filteredRows].sort((left, right) => {
      const leftValue = cellValue(left, sortKey);
      const rightValue = cellValue(right, sortKey);
      const comparison = leftValue.localeCompare(rightValue, undefined, {
        numeric: true,
        sensitivity: "base",
      });
      return sortDirection === "asc" ? comparison : -comparison;
    });
  }, [filteredRows, sortDirection, sortKey]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / safePageSize));
  const currentPageIndex = Math.min(pageIndex, pageCount - 1);
  const pageRows = sortedRows.slice(
    currentPageIndex * safePageSize,
    currentPageIndex * safePageSize + safePageSize,
  );
  const allSelected = pageRows.length > 0 && pageRows.every((row) => selectedIds.includes(row.id));

  function toggleSort(key: keyof T & string) {
    if (sortKey === key) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("asc");
  }

  function toggleColumn(key: string) {
    setVisibleColumns((current) => {
      const next = new Set(current);
      if (next.has(key) && next.size > 1) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function exportCsv() {
    const header = visibleColumnList.map((column) => column.label);
    const body = sortedRows.map((row) =>
      visibleColumnList.map((column) => cellValue(row, column.key)),
    );
    const csv = [header, ...body]
      .map((line) =>
        line.map((value) => `"${value.replaceAll('"', '""')}"`).join(","),
      )
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `admin-${savedViewsKey}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function saveView() {
    window.localStorage.setItem(
      `admin-table-view:${savedViewsKey}`,
      JSON.stringify({
        filters,
        search,
        sortDirection,
        sortKey,
        visibleColumns: Array.from(visibleColumns),
      }),
    );
  }

  function loadView() {
    const raw = window.localStorage.getItem(`admin-table-view:${savedViewsKey}`);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw) as {
      filters?: Record<string, string>;
      search?: string;
      sortDirection?: "asc" | "desc";
      sortKey?: keyof T & string;
      visibleColumns?: string[];
    };
    setFilters(parsed.filters ?? {});
    setSearch(parsed.search ?? "");
    setSortDirection(parsed.sortDirection ?? "asc");
    setSortKey(parsed.sortKey ?? columns[0]?.key ?? "id");
    setVisibleColumns(new Set(parsed.visibleColumns ?? columns.map((column) => column.key)));
  }

  return (
    <div className="space-y-3">
      <BulkActionBar
        selectedCount={selectedIds.length}
        onSuspend={() => onBulkSuspend?.(selectedIds)}
        onClear={() => onSelectedIdsChange?.([])}
      />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-md flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPageIndex(0);
            }}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={saveView}>
            Save view
          </Button>
          <Button variant="outline" size="sm" onClick={loadView}>
            Load view
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv}>
            <Download className="h-4 w-4" />
            CSV
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {columns.map((column) => (
          <Button
            key={column.key}
            variant={visibleColumns.has(column.key) ? "secondary" : "outline"}
            size="sm"
            onClick={() => toggleColumn(column.key)}
          >
            <EyeOff className="h-4 w-4" />
            {column.label}
          </Button>
        ))}
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {columns
          .filter((column) => column.filterable !== false)
          .slice(0, 3)
          .map((column) => (
            <Input
              key={column.key}
              value={filters[column.key] ?? ""}
              placeholder={`Filter ${column.label}`}
              onChange={(event) => {
                setFilters((current) => ({
                  ...current,
                  [column.key]: event.target.value,
                }));
                setPageIndex(0);
              }}
            />
          ))}
      </div>
      <div className="overflow-hidden rounded-md border bg-card">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">
                  <Checkbox
                    checked={allSelected}
                    onChange={(event) =>
                      onSelectedIdsChange?.(
                        event.target.checked ? pageRows.map((row) => row.id) : [],
                      )
                    }
                    aria-label="Select all rows"
                  />
                </TableHead>
                {visibleColumnList.map((column) => (
                  <TableHead key={column.key}>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-medium"
                      onClick={() => toggleSort(column.key)}
                    >
                      {column.label}
                      {sortKey === column.key ? (
                        <span className="text-xs text-muted-foreground">{sortDirection}</span>
                      ) : null}
                    </button>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {pageRows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Checkbox
                      checked={selectedIds.includes(row.id)}
                      onChange={(event) => {
                        const next = event.target.checked
                          ? [...selectedIds, row.id]
                          : selectedIds.filter((id) => id !== row.id);
                        onSelectedIdsChange?.(next);
                      }}
                      aria-label={`Select ${row.id}`}
                    />
                  </TableCell>
                  {visibleColumnList.map((column) => (
                    <TableCell key={column.key}>
                      {column.render ? column.render(row) : String(row[column.key] ?? "")}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              {pageRows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={visibleColumnList.length + 1} className="h-24 text-center text-muted-foreground">
                    No rows
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {safePageSize} per page, {sortedRows.length} shown
          {totalRows !== undefined ? ` of ${totalRows}` : ""}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={currentPageIndex === 0}
            onClick={() => setPageIndex((current) => Math.max(0, current - 1))}
          >
            <ChevronLeft className="h-4 w-4" />
            Previous
          </Button>
          <span>
            Page {currentPageIndex + 1} of {pageCount}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={currentPageIndex >= pageCount - 1}
            onClick={() => setPageIndex((current) => Math.min(pageCount - 1, current + 1))}
          >
            Next
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
