"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { Plus, Search } from "lucide-react";
import { AdminPage } from "@/components/features/admin/AdminPage";
import { TenantStatusBadge } from "@/components/features/admin/TenantStatusBadge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useAdminTenants,
  type TenantAdminView,
} from "@/lib/hooks/use-admin-tenants";
import { HelpContent } from "./help";

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Tenant inventory could not be loaded";
}

export default function TenantsPage() {
  const [search, setSearch] = useState("");
  const listParams = useMemo(() => {
    const query = search.trim();
    return query ? { q: query, limit: 100 } : { limit: 100 };
  }, [search]);
  const { data, error, isLoading } = useAdminTenants(listParams);

  const columns = useMemo<ColumnDef<TenantAdminView>[]>(
    () => [
      {
        accessorKey: "slug",
        header: "Slug",
        cell: ({ row }) => (
          <Link
            className="font-medium text-primary hover:underline"
            href={`/admin/tenants/${row.original.id}`}
          >
            {row.original.slug}
          </Link>
        ),
      },
      {
        accessorKey: "kind",
        header: "Kind",
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <TenantStatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "member_count",
        header: "Members",
      },
      {
        accessorKey: "active_workspace_count",
        header: "Workspaces",
      },
      {
        accessorKey: "created_at",
        header: "Created",
        cell: ({ row }) => formatDate(row.original.created_at),
      },
    ],
    [],
  );

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <AdminPage
      title="Tenants"
      description="Platform tenant inventory."
      help={<HelpContent />}
      actions={
        <Button asChild size="sm">
          <Link href="/admin/tenants/new">
            <Plus className="h-4 w-4" />
            Provision new tenant
          </Link>
        </Button>
      }
    >
      <div className="space-y-4">
        <div className="relative max-w-md">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            className="pl-9"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search tenants"
            value={search}
          />
        </div>

        {error ? (
          <Alert variant="destructive">
            <AlertTitle>Tenants unavailable</AlertTitle>
            <AlertDescription>{errorMessage(error)}</AlertDescription>
          </Alert>
        ) : null}

        <div className="overflow-hidden rounded-md border bg-card">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <TableHead key={header.id}>
                        {header.isPlaceholder
                          ? null
                          : flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {isLoading ? (
                  Array.from({ length: 5 }, (_, index) => (
                    <TableRow key={index}>
                      {columns.map((_column, columnIndex) => (
                        <TableCell key={columnIndex}>
                          <Skeleton className="h-5 w-full max-w-36" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : table.getRowModel().rows.length > 0 ? (
                  table.getRowModel().rows.map((row) => (
                    <TableRow key={row.id}>
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell
                      className="h-24 text-center text-muted-foreground"
                      colSpan={columns.length}
                    >
                      No tenants
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </div>
    </AdminPage>
  );
}
