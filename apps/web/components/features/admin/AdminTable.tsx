"use client";

import { Download, Search } from "lucide-react";
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
}

interface AdminTableProps<T extends { id: string }> {
  columns: AdminTableColumn<T>[];
  rows: T[];
  selectedIds?: string[];
  onSelectedIdsChange?: (ids: string[]) => void;
}

export function AdminTable<T extends { id: string }>({
  columns,
  rows,
  selectedIds = [],
  onSelectedIdsChange,
}: AdminTableProps<T>) {
  const allSelected = rows.length > 0 && rows.every((row) => selectedIds.includes(row.id));

  return (
    <div className="space-y-3">
      <BulkActionBar
        selectedCount={selectedIds.length}
        onClear={() => onSelectedIdsChange?.([])}
      />
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-md flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search" />
        </div>
        <Button variant="outline" size="sm">
          <Download className="h-4 w-4" />
          CSV
        </Button>
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
                      onSelectedIdsChange?.(event.target.checked ? rows.map((row) => row.id) : [])
                    }
                    aria-label="Select all rows"
                  />
                </TableHead>
                {columns.map((column) => (
                  <TableHead key={column.key}>{column.label}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
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
                  {columns.map((column) => (
                    <TableCell key={column.key}>
                      {column.render ? column.render(row) : String(row[column.key] ?? "")}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={columns.length + 1} className="h-24 text-center text-muted-foreground">
                    No rows
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </div>
      <div className="text-xs text-muted-foreground">50 per page</div>
    </div>
  );
}
