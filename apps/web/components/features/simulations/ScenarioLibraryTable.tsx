"use client";

import { type ColumnDef } from "@tanstack/react-table";
import { Archive, Pencil, Play } from "lucide-react";
import { DataTable } from "@/components/shared/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { SimulationScenario } from "@/types/simulation";

export interface ScenarioLibraryTableProps {
  scenarios: SimulationScenario[];
  isLoading?: boolean;
  onOpen: (scenarioId: string) => void;
  onEdit: (scenarioId: string) => void;
  onArchive: (scenarioId: string) => void;
  onLaunch: (scenario: SimulationScenario) => void;
}

export function ScenarioLibraryTable({
  scenarios,
  isLoading = false,
  onOpen,
  onEdit,
  onArchive,
  onLaunch,
}: ScenarioLibraryTableProps) {
  const columns: ColumnDef<SimulationScenario>[] = [
    {
      accessorKey: "name",
      header: "Name",
      cell: ({ row }) => (
        <div>
          <div className="font-medium">{row.original.name}</div>
          <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
            {row.original.description ?? "No description"}
          </div>
        </div>
      ),
    },
    {
      id: "agents",
      header: "Agents",
      cell: ({ row }) => {
        const agents = agentCount(row.original);
        return agents === 1 ? "1 agent" : `${agents} agents`;
      },
    },
    {
      id: "lastRun",
      header: "Last run",
      cell: () => <span className="text-muted-foreground">Not run</span>,
    },
    {
      id: "state",
      header: "State",
      cell: ({ row }) =>
        row.original.archived_at ? (
          <Badge variant="outline">Archived</Badge>
        ) : (
          <Badge className="bg-emerald-500/15 text-emerald-700" variant="secondary">
            Active
          </Badge>
        ),
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <div className="flex justify-end gap-2" onClick={(event) => event.stopPropagation()}>
          <Button
            aria-label={`Launch ${row.original.name}`}
            disabled={Boolean(row.original.archived_at)}
            disabledByMaintenance
            size="icon"
            variant="ghost"
            onClick={() => onLaunch(row.original)}
          >
            <Play className="h-4 w-4" />
          </Button>
          <Button
            aria-label={`Edit ${row.original.name}`}
            size="icon"
            variant="ghost"
            onClick={() => onEdit(row.original.id)}
          >
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            aria-label={`Archive ${row.original.name}`}
            disabled={Boolean(row.original.archived_at)}
            size="icon"
            variant="ghost"
            onClick={() => onArchive(row.original.id)}
          >
            <Archive className="h-4 w-4" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={scenarios}
      emptyStateMessage="No simulation scenarios found."
      getRowAriaLabel={(scenario) => `Open scenario ${scenario.name}`}
      isLoading={isLoading}
      onRowClick={(scenario) => onOpen(scenario.id)}
    />
  );
}

function agentCount(scenario: SimulationScenario) {
  const raw = scenario.agents_config.agents ?? scenario.agents_config.agent_fqns;
  return Array.isArray(raw) ? raw.length : 0;
}
