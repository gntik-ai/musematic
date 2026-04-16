"use client";

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { formatDistanceToNow } from "date-fns";
import { Layers3 } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AgentMaturityBadge } from "@/components/features/agent-management/AgentMaturityBadge";
import { AgentStatusBadge } from "@/components/features/agent-management/AgentStatusBadge";
import { DataTable } from "@/components/shared/DataTable";
import { FilterBar, type FilterDefinition } from "@/components/shared/FilterBar";
import { SearchInput } from "@/components/shared/SearchInput";
import { Button } from "@/components/ui/button";
import { useAgents } from "@/lib/hooks/use-agents";
import { useNamespaces } from "@/lib/hooks/use-namespaces";
import { parseAgentCatalogFilters, serializeAgentCatalogFilters } from "@/lib/schemas/agent-management";
import {
  AGENT_MATURITIES,
  AGENT_STATUSES,
  buildAgentManagementHref,
  type AgentCatalogEntry,
} from "@/lib/types/agent-management";
import { toTitleCase } from "@/lib/utils";

export interface AgentDataTableProps {
  workspace_id: string;
}

export function AgentDataTable({ workspace_id }: AgentDataTableProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(
    () => parseAgentCatalogFilters(searchParams),
    [searchParams],
  );
  const agentsQuery = useAgents(filters, { workspaceId: workspace_id });
  const namespacesQuery = useNamespaces(workspace_id);

  const filterDefinitions = useMemo<FilterDefinition[]>(
    () => [
      {
        id: "namespace",
        label: "Namespace",
        value: filters.namespace,
        multiple: true,
        options: (namespacesQuery.data ?? []).map((item) => ({
          label: `${item.namespace} (${item.agent_count})`,
          value: item.namespace,
        })),
      },
      {
        id: "maturity",
        label: "Maturity",
        value: filters.maturity,
        multiple: true,
        options: AGENT_MATURITIES.map((maturity) => ({
          label: toTitleCase(maturity),
          value: maturity,
        })),
      },
      {
        id: "status",
        label: "Status",
        value: filters.status,
        multiple: true,
        options: AGENT_STATUSES.map((status) => ({
          label: toTitleCase(status),
          value: status,
        })),
      },
    ],
    [filters.maturity, filters.namespace, filters.status, namespacesQuery.data],
  );

  const columns = useMemo<ColumnDef<AgentCatalogEntry>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Agent",
        cell: ({ row }) => (
          <a
            className="block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            href={buildAgentManagementHref(row.original.fqn)}
          >
            <div className="space-y-1">
              <p className="font-medium">{row.original.name}</p>
              <p className="text-xs text-muted-foreground">{row.original.fqn}</p>
            </div>
          </a>
        ),
      },
      {
        accessorKey: "maturity_level",
        header: "Maturity",
        cell: ({ row }) => (
          <AgentMaturityBadge maturity={row.original.maturity_level} size="sm" />
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <AgentStatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "revision_count",
        header: "Revisions",
        cell: ({ row }) => row.original.revision_count,
      },
      {
        accessorKey: "updated_at",
        header: "Updated",
        cell: ({ row }) =>
          formatDistanceToNow(new Date(row.original.updated_at), {
            addSuffix: true,
          }),
      },
    ],
    [],
  );

  const updateSearchParams = (
    nextValues: Partial<ReturnType<typeof parseAgentCatalogFilters>>,
  ) => {
    const nextQuery = serializeAgentCatalogFilters({
      ...filters,
      ...nextValues,
      cursor: null,
    }).toString();

    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="w-full max-w-xl">
          <SearchInput
            defaultValue={filters.search}
            isLoading={agentsQuery.isFetching && !agentsQuery.isFetchingNextPage}
            placeholder="Search agents"
            onChange={(value) => updateSearchParams({ search: value })}
          />
        </div>
        <p className="text-sm text-muted-foreground">
          {agentsQuery.total} agents in view
        </p>
      </div>
      <FilterBar
        filters={filterDefinitions}
        onChange={(id, value) => {
          updateSearchParams({
            [id]: Array.isArray(value) ? value : value ? [value] : [],
          });
        }}
        onClear={() =>
          updateSearchParams({
            namespace: [],
            maturity: [],
            status: [],
            search: "",
          })
        }
      />
      <DataTable
        columns={columns}
        data={agentsQuery.agents}
        enableFiltering={false}
        emptyStateMessage="No agents match the active filters."
        hidePagination
        isLoading={agentsQuery.isLoading}
      />
      {agentsQuery.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            className="gap-2"
            disabled={agentsQuery.isFetchingNextPage}
            variant="outline"
            onClick={() => {
              void agentsQuery.fetchNextPage();
            }}
          >
            <Layers3 className="h-4 w-4" />
            {agentsQuery.isFetchingNextPage ? "Loading more…" : "Load more"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
