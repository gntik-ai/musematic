"use client";

/**
 * UPD-050 — Suspension queue table.
 *
 * Renders rows from `useSuspensions`. Each row links to the detail page
 * at `/admin/security/suspensions/[id]`.
 */

import Link from "next/link";
import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSuspensions } from "@/lib/hooks/use-suspensions";
import type { SuspensionView } from "@/lib/security/types";

function formatAge(suspendedAt: string): string {
  const minutes = Math.floor((Date.now() - new Date(suspendedAt).getTime()) / 60000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

export function SuspensionTable() {
  const [status, setStatus] = useState<"active" | "lifted" | "all">("active");
  const { data, isLoading, isError, refetch } = useSuspensions(status);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }
  if (isError) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
        Could not load suspensions. Try refreshing.
      </div>
    );
  }
  const items = data?.items ?? [];
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {(["active", "lifted", "all"] as const).map((value) => (
          <Button
            key={value}
            variant={status === value ? "default" : "outline"}
            size="sm"
            onClick={() => setStatus(value)}
            data-testid={`suspensions-filter-${value}`}
          >
            {value === "active" ? "Active" : value === "lifted" ? "Lifted" : "All"}
          </Button>
        ))}
        <Button variant="ghost" size="sm" onClick={() => void refetch()}>
          Refresh
        </Button>
      </div>
      {items.length === 0 ? (
        <div className="rounded-md border p-8 text-center text-muted-foreground">
          No suspensions in this view.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>By</TableHead>
              <TableHead>Age</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((row: SuspensionView) => (
              <TableRow key={row.id} data-testid={`suspension-row-${row.id}`}>
                <TableCell>
                  <Link
                    href={`/admin/security/suspensions/${row.id}`}
                    className="font-mono hover:underline"
                  >
                    {row.user_id}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{row.reason}</Badge>
                </TableCell>
                <TableCell>{row.suspended_by}</TableCell>
                <TableCell>{formatAge(row.suspended_at)}</TableCell>
                <TableCell>
                  {row.lifted_at ? (
                    <Badge variant="outline">Lifted</Badge>
                  ) : (
                    <Badge>Active</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
