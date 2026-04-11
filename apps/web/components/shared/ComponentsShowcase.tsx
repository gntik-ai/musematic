"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Bot, Filter, Layers3 } from "lucide-react";
import { CodeBlock } from "@/components/shared/CodeBlock";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { DataTable } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FilterBar } from "@/components/shared/FilterBar";
import { JsonViewer } from "@/components/shared/JsonViewer";
import { MetricCard } from "@/components/shared/MetricCard";
import { ScoreGauge } from "@/components/shared/ScoreGauge";
import { SearchInput } from "@/components/shared/SearchInput";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Timeline } from "@/components/shared/Timeline";

interface AgentRow {
  name: string;
  status: "healthy" | "warning" | "running";
  owner: string;
}

const rows: AgentRow[] = [
  { name: "Reasoning Engine", status: "healthy", owner: "Ops" },
  { name: "Runtime Controller", status: "running", owner: "Platform" },
  { name: "Sandbox Manager", status: "warning", owner: "Security" },
];

export function ComponentsShowcase() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const [filters, setFilters] = useState([
    {
      id: "status",
      label: "Status",
      value: "",
      options: [
        { label: "Healthy", value: "healthy" },
        { label: "Running", value: "running" },
        { label: "Warning", value: "warning" },
      ],
    },
  ]);

  const columns = useMemo<ColumnDef<AgentRow>[]>(
    () => [
      { accessorKey: "name", header: "Agent", cell: ({ row }) => row.original.name },
      { accessorKey: "status", header: "Status", cell: ({ row }) => <StatusBadge status={row.original.status} /> },
      { accessorKey: "owner", header: "Owner", cell: ({ row }) => row.original.owner },
    ],
    [],
  );

  const filteredRows = rows.filter((row) => {
    const statusFilter = filters[0]?.value;
    const searchMatch = row.name.toLowerCase().includes(searchValue.toLowerCase());
    const statusMatch = statusFilter ? row.status === statusFilter : true;
    return searchMatch && statusMatch;
  });

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">Development</p>
        <h1 className="mt-2 text-3xl font-semibold">Shared component showcase</h1>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <MetricCard
          sparklineData={[
            { timestamp: "2026-04-11T08:00:00.000Z", value: 78 },
            { timestamp: "2026-04-11T09:00:00.000Z", value: 82 },
            { timestamp: "2026-04-11T10:00:00.000Z", value: 87 },
          ]}
          title="Agent uptime"
          trend="up"
          trendValue="+12% this week"
          unit="%"
          value={99.2}
        />
        <MetricCard title="Policy drift" trend="down" trendValue="-4 incidents" value={3} />
        <div className="rounded-2xl border border-border bg-card/80 p-6">
          <ScoreGauge label="Trust score" score={81} />
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.3fr,0.7fr]">
        <div className="space-y-4">
          <SearchInput placeholder="Search showcased agents" onChange={setSearchValue} />
          <FilterBar
            filters={filters}
            onChange={(id, value) =>
              setFilters((current) =>
                current.map((filter) => (filter.id === id ? { ...filter, value } : filter)),
              )
            }
            onClear={() => setFilters((current) => current.map((filter) => ({ ...filter, value: "" })))}
          />
          <DataTable columns={columns} data={filteredRows} />
        </div>
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <StatusBadge status="healthy" />
            <StatusBadge status="warning" />
            <StatusBadge status="error" />
            <StatusBadge status="inactive" />
            <StatusBadge status="pending" />
            <StatusBadge status="running" />
          </div>
          <EmptyState
            ctaLabel="Trigger dialog"
            description="Use this surface to validate spacing, typography, and CTA treatments."
            icon={Layers3}
            onCtaClick={() => setDialogOpen(true)}
            title="Empty state treatment"
          />
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[0.95fr,1.05fr]">
        <JsonViewer
          maxDepth={1}
          value={{
            agent: "runtime-controller",
            mode: "streaming",
            connected: true,
            workspaces: ["signal-lab", "trust-foundry"],
            thresholds: { warning: 40, good: 75 },
          }}
        />
        <CodeBlock
          code={`import { createApiClient } from "@/lib/api";\n\nconst api = createApiClient(process.env.NEXT_PUBLIC_API_URL!);\nawait api.get("/api/v1/workspaces");`}
        />
      </div>
      <Timeline
        events={[
          {
            id: "1",
            timestamp: "2026-04-11T08:10:00.000Z",
            label: "Runtime controller promoted",
            description: "Blue/green handoff completed for workspace orchestration jobs.",
            status: "healthy",
          },
          {
            id: "2",
            timestamp: "2026-04-11T09:15:00.000Z",
            label: "Sandbox manager latency spike",
            description: "P95 exceeded guardrail for 4 minutes, then self-recovered.",
            status: "warning",
          },
        ]}
      />
      <ConfirmDialog
        description="This dialog demonstrates destructive confirmation handling without auto-closing."
        onConfirm={() => setDialogOpen(false)}
        onOpenChange={setDialogOpen}
        open={dialogOpen}
        title="Purge inactive agents?"
        variant="destructive"
      />
      <div className="grid gap-4 rounded-2xl border border-dashed border-border p-6 lg:grid-cols-3">
        <EmptyState description="Compact card footprint" icon={Bot} title="Micro empty state" />
        <div className="rounded-xl border border-border bg-card/80 p-5">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Inline gauge</p>
          <ScoreGauge score={56} size={80} />
        </div>
        <div className="rounded-xl border border-border bg-card/80 p-5">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.16em] text-muted-foreground">Filter affordance</p>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Filter className="h-4 w-4" />
            Filters stay keyboard-friendly and responsive.
          </div>
        </div>
      </div>
    </div>
  );
}
