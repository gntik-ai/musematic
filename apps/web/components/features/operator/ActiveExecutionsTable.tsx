"use client";

import { useEffect, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { format } from "date-fns";
import { Copy, TimerReset } from "lucide-react";
import { ActiveExecutionStatusBadge } from "@/components/features/operator/ActiveExecutionStatusBadge";
import { DataTable } from "@/components/shared/DataTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { useToast } from "@/lib/hooks/use-toast";
import {
  ACTIVE_EXECUTION_STATUS_LABELS,
  type ActiveExecution,
  type ActiveExecutionsFilters,
} from "@/lib/types/operator-dashboard";

export interface ActiveExecutionsTableProps {
  executions: ActiveExecution[];
  totalCount: number;
  isLoading: boolean;
  filters: ActiveExecutionsFilters;
  onFiltersChange: (filters: Partial<ActiveExecutionsFilters>) => void;
  onRowClick: (executionId: string) => void;
}

function formatElapsed(elapsedMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(elapsedMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

export function ActiveExecutionsTable({
  executions,
  totalCount,
  isLoading,
  filters,
  onFiltersChange,
  onRowClick,
}: ActiveExecutionsTableProps) {
  const { toast } = useToast();
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const interval = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => {
      window.clearInterval(interval);
    };
  }, []);

  const visibleExecutions = useMemo(() => {
    const filtered =
      filters.status === "all"
        ? executions
        : executions.filter((execution) => execution.status === filters.status);
    const withElapsed = filtered.map((execution) => ({
      ...execution,
      elapsedMs: Math.max(
        execution.elapsedMs,
        now - new Date(execution.startedAt).getTime(),
      ),
    }));

    return [...withElapsed].sort((left, right) => {
      if (filters.sortBy === "elapsed") {
        return right.elapsedMs - left.elapsedMs;
      }

      return (
        new Date(right.startedAt).getTime() -
        new Date(left.startedAt).getTime()
      );
    });
  }, [executions, filters.sortBy, filters.status, now]);

  const columns = useMemo<ColumnDef<ActiveExecution>[]>(
    () => [
      {
        accessorKey: "id",
        header: "Execution",
        cell: ({ row }) => (
          <div className="flex items-center gap-2">
            <a
              className="rounded-md font-mono text-sm underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              href={`/operator/executions/${encodeURIComponent(row.original.id)}`}
            >
              {row.original.id.slice(0, 8)}
            </a>
            <Button
              aria-label={`Copy execution id ${row.original.id}`}
              size="icon"
              variant="ghost"
              onClick={(event) => {
                event.stopPropagation();
                void navigator.clipboard.writeText(row.original.id).then(() => {
                  toast({
                    title: "Execution id copied",
                    variant: "success",
                  });
                });
              }}
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        ),
      },
      {
        accessorKey: "agentFqn",
        header: "Agent",
      },
      {
        accessorKey: "workflowName",
        header: "Workflow",
      },
      {
        accessorKey: "currentStepLabel",
        header: "Current step",
        cell: ({ row }) => row.original.currentStepLabel ?? "—",
      },
      {
        id: "status",
        header: "Status",
        cell: ({ row }) => (
          <ActiveExecutionStatusBadge status={row.original.status} />
        ),
      },
      {
        accessorKey: "startedAt",
        header: "Started",
        cell: ({ row }) => format(new Date(row.original.startedAt), "PPp"),
      },
      {
        id: "elapsed",
        header: "Elapsed",
        cell: ({ row }) => (
          <span className="inline-flex items-center gap-2 font-mono text-sm">
            <TimerReset className="h-4 w-4 text-muted-foreground" />
            {formatElapsed(row.original.elapsedMs)}
          </span>
        ),
      },
    ],
    [toast],
  );

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <CardTitle>Active executions</CardTitle>
          <p className="text-sm text-muted-foreground">
            Running work across the current workspace with live elapsed timers.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>Status</span>
            <Select
              aria-label="Execution status filter"
              value={filters.status}
              onChange={(event) =>
                onFiltersChange({
                  status: event.target.value as ActiveExecutionsFilters["status"],
                })
              }
            >
              <option value="all">All</option>
              <option value="running">{ACTIVE_EXECUTION_STATUS_LABELS.running}</option>
              <option value="paused">{ACTIVE_EXECUTION_STATUS_LABELS.paused}</option>
              <option value="waiting_for_approval">
                {ACTIVE_EXECUTION_STATUS_LABELS.waiting_for_approval}
              </option>
              <option value="compensating">
                {ACTIVE_EXECUTION_STATUS_LABELS.compensating}
              </option>
            </Select>
          </label>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>Sort</span>
            <Select
              aria-label="Execution sort order"
              value={filters.sortBy}
              onChange={(event) =>
                onFiltersChange({
                  sortBy: event.target.value as ActiveExecutionsFilters["sortBy"],
                })
              }
            >
              <option value="started_at">Started</option>
              <option value="elapsed">Elapsed</option>
            </Select>
          </label>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {totalCount} executions in view
        </p>
        <DataTable
          columns={columns}
          data={visibleExecutions}
          enableFiltering={false}
          enableSorting={false}
          emptyStateMessage="No active executions"
          getRowAriaLabel={(row) => `Open execution ${row.id}`}
          hidePagination
          isLoading={isLoading}
          onRowClick={(row) => onRowClick(row.id)}
        />
      </CardContent>
    </Card>
  );
}
