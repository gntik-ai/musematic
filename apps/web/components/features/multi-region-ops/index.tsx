"use client";

import { useMemo } from "react";
import {
  Activity,
  AlertTriangle,
  Clock,
  ExternalLink,
  Gauge,
  Server,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  type CapacitySignalResponse,
  type FailoverPlanResponse,
  type MaintenanceWindowResponse,
  type RegionConfigResponse,
  type ReplicationHealth,
  type ReplicationStatusResponse,
  useActiveMaintenanceWindow,
  useCapacityOverview,
  useFailoverPlans,
  useMaintenanceWindows,
  useRegions,
  useReplicationStatus,
  useUpgradeStatus,
} from "@/lib/api/regions";
import { cn } from "@/lib/utils";

const RUNBOOKS = [
  { label: "Failover", href: "/docs/runbooks/failover.md" },
  { label: "Zero-downtime upgrade", href: "/docs/runbooks/zero-downtime-upgrade.md" },
  { label: "Active-active", href: "/docs/runbooks/active-active-considerations.md" },
] as const;

const HEALTH_TONE: Record<ReplicationHealth, string> = {
  healthy: "bg-emerald-500/10 text-emerald-700",
  degraded: "bg-amber-500/10 text-amber-700",
  unhealthy: "bg-red-500/10 text-red-700",
  paused: "bg-sky-500/10 text-sky-700",
};

function formatDate(value?: string | null) {
  if (!value) {
    return "Not recorded";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString();
}

function formatSeconds(value?: number | null) {
  if (value === null || value === undefined) {
    return "No sample";
  }
  if (value < 60) {
    return `${value}s`;
  }
  return `${Math.round(value / 60)}m`;
}

function numericField(source: Record<string, unknown> | null | undefined, keys: string[]) {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
      return Number(value);
    }
  }
  return null;
}

function healthBadge(health: ReplicationHealth) {
  return (
    <Badge className={HEALTH_TONE[health]} variant="secondary">
      {health}
    </Badge>
  );
}

function SummaryTile({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof Activity;
  label: string;
  value: string | number;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-background p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icon className={cn("h-4 w-4", tone)} />
        {label}
      </div>
      <p className="mt-3 text-2xl font-semibold tracking-tight">{value}</p>
    </div>
  );
}

export function RunbookLinks({ includeCost = false }: { includeCost?: boolean }) {
  return (
    <div className="flex flex-wrap gap-2">
      {RUNBOOKS.map((link) => (
        <Button key={link.href} asChild size="sm" variant="outline">
          <a href={link.href}>
            <ExternalLink className="h-4 w-4" />
            {link.label}
          </a>
        </Button>
      ))}
      {includeCost ? (
        <Button asChild size="sm" variant="outline">
          <a href="/costs">
            <Gauge className="h-4 w-4" />
            Costs
          </a>
        </Button>
      ) : null}
    </div>
  );
}

export function RegionsPanel() {
  const regionsQuery = useRegions();
  const replicationQuery = useReplicationStatus();
  const failoverPlansQuery = useFailoverPlans();
  const upgradeStatusQuery = useUpgradeStatus();

  const regions = regionsQuery.data ?? [];
  const replicationRows = replicationQuery.data?.items ?? [];
  const failoverPlans = failoverPlansQuery.data ?? [];
  const unhealthyCount = replicationRows.filter(
    (row) => row.health === "unhealthy" || row.missing_probe,
  ).length;
  const stalePlans = failoverPlans.filter((plan) => plan.is_stale).length;
  const enabledRegions = regions.filter((region) => region.enabled);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Regions</h3>
          <p className="text-sm text-muted-foreground">
            {replicationQuery.data
              ? `Last sampled ${formatDate(replicationQuery.data.generated_at)}`
              : "Waiting for replication samples"}
          </p>
        </div>
        <RunbookLinks />
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <SummaryTile icon={Server} label="Enabled regions" value={enabledRegions.length} />
        <SummaryTile icon={Activity} label="Replication rows" value={replicationRows.length} />
        <SummaryTile
          icon={AlertTriangle}
          label="Unhealthy gaps"
          tone={unhealthyCount > 0 ? "text-red-600" : "text-emerald-600"}
          value={unhealthyCount}
        />
        <SummaryTile icon={Clock} label="Stale plans" value={stalePlans} />
      </div>

      <ReplicationStatusTable rows={replicationRows} />
      <FailoverPlanList plans={failoverPlans} />
      <UpgradeStatus versions={upgradeStatusQuery.data?.runtime_versions ?? []} />
      {regions.length > 0 ? <RegionList regions={regions} /> : null}
    </div>
  );
}

function ReplicationStatusTable({ rows }: { rows: ReplicationStatusResponse[] }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background">
      <div className="flex items-center gap-2 border-b border-border/70 px-4 py-3">
        <ShieldCheck className="h-4 w-4 text-muted-foreground" />
        <h4 className="font-medium">Replication status</h4>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Component</TableHead>
              <TableHead>Route</TableHead>
              <TableHead>Health</TableHead>
              <TableHead>Lag</TableHead>
              <TableHead>Threshold</TableHead>
              <TableHead>Measured</TableHead>
              <TableHead>Detail</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell className="text-muted-foreground" colSpan={7}>
                  No replication samples yet.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow key={`${row.source_region}-${row.target_region}-${row.component}`}>
                  <TableCell className="font-medium">{row.component}</TableCell>
                  <TableCell>
                    {row.source_region} -&gt; {row.target_region}
                  </TableCell>
                  <TableCell>{healthBadge(row.health)}</TableCell>
                  <TableCell>{formatSeconds(row.lag_seconds)}</TableCell>
                  <TableCell>{formatSeconds(row.threshold_seconds)}</TableCell>
                  <TableCell>{formatDate(row.measured_at)}</TableCell>
                  <TableCell className="max-w-[18rem] truncate text-muted-foreground">
                    {row.pause_reason ??
                      row.error_detail ??
                      (row.missing_probe ? "Missing replication path" : "Recorded")}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function FailoverPlanList({ plans }: { plans: FailoverPlanResponse[] }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background">
      <div className="flex items-center gap-2 border-b border-border/70 px-4 py-3">
        <Wrench className="h-4 w-4 text-muted-foreground" />
        <h4 className="font-medium">Failover plans</h4>
      </div>
      <div className="divide-y divide-border/70">
        {plans.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">No failover plans configured.</p>
        ) : (
          plans.map((plan) => (
            <article key={plan.id} className="grid gap-3 p-4 md:grid-cols-[1fr_auto]">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h5 className="font-medium">{plan.name}</h5>
                  {plan.is_stale ? (
                    <Badge className="bg-amber-500/10 text-amber-700" variant="secondary">
                      stale
                    </Badge>
                  ) : (
                    <Badge className="bg-emerald-500/10 text-emerald-700" variant="secondary">
                      rehearsed
                    </Badge>
                  )}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {plan.from_region} -&gt; {plan.to_region} · {plan.steps.length} steps · tested{" "}
                  {formatDate(plan.tested_at)}
                </p>
              </div>
              {plan.runbook_url ? (
                <Button asChild size="sm" variant="outline">
                  <a href={plan.runbook_url}>
                    <ExternalLink className="h-4 w-4" />
                    Runbook
                  </a>
                </Button>
              ) : null}
            </article>
          ))
        )}
      </div>
    </div>
  );
}

function UpgradeStatus({
  versions,
}: {
  versions: Array<{ runtime_id: string; version: string; status: string; coexistence_until?: string | null }>;
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="h-4 w-4 text-muted-foreground" />
        <h4 className="font-medium">Runtime versions</h4>
      </div>
      {versions.length === 0 ? (
        <p className="text-sm text-muted-foreground">No runtime version manifest available.</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {versions.map((version) => (
            <div key={`${version.runtime_id}-${version.version}`} className="rounded-lg border p-3">
              <p className="font-medium">{version.runtime_id}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {version.version} · {version.status}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Coexistence until {formatDate(version.coexistence_until)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RegionList({ regions }: { regions: RegionConfigResponse[] }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {regions.map((region) => (
        <div key={region.id} className="rounded-lg border border-border/70 bg-background p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium">{region.region_code}</p>
            <Badge variant={region.enabled ? "secondary" : "outline"}>{region.region_role}</Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            RPO {region.rpo_target_minutes}m · RTO {region.rto_target_minutes}m
          </p>
        </div>
      ))}
    </div>
  );
}

export function MaintenancePanel() {
  const activeQuery = useActiveMaintenanceWindow();
  const windowsQuery = useMaintenanceWindows();
  const activeWindow = activeQuery.data ?? null;
  const windows = windowsQuery.data ?? [];

  const sortedWindows = useMemo(
    () =>
      [...windows].sort(
        (left, right) => new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime(),
      ),
    [windows],
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Maintenance</h3>
          <p className="text-sm text-muted-foreground">
            {activeWindow ? "Active write gate" : "No active write gate"}
          </p>
        </div>
        <RunbookLinks />
      </div>

      <ActiveWindowBanner window={activeWindow} />

      <div className="rounded-lg border border-border/70 bg-background">
        <div className="flex items-center gap-2 border-b border-border/70 px-4 py-3">
          <Clock className="h-4 w-4 text-muted-foreground" />
          <h4 className="font-medium">Windows</h4>
        </div>
        <div className="divide-y divide-border/70">
          {sortedWindows.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No maintenance windows scheduled.</p>
          ) : (
            sortedWindows.map((window) => <MaintenanceWindowRow key={window.id} window={window} />)
          )}
        </div>
      </div>
    </div>
  );
}

function ActiveWindowBanner({ window }: { window: MaintenanceWindowResponse | null }) {
  if (!window) {
    return (
      <div className="rounded-lg border border-border/70 bg-background p-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-600" />
          <p className="font-medium">Writes open</p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-700" />
            <p className="font-medium">Maintenance active until {formatDate(window.ends_at)}</p>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {window.announcement_text ?? window.reason ?? "Planned maintenance"}
          </p>
        </div>
        {window.blocks_writes ? (
          <Badge className="bg-amber-500/20 text-amber-800" variant="secondary">
            writes blocked
          </Badge>
        ) : null}
      </div>
    </div>
  );
}

function MaintenanceWindowRow({ window }: { window: MaintenanceWindowResponse }) {
  return (
    <article className="grid gap-3 p-4 md:grid-cols-[1fr_auto]">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium">{window.reason ?? "Maintenance window"}</p>
          <Badge variant={window.status === "active" ? "default" : "secondary"}>
            {window.status}
          </Badge>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {formatDate(window.starts_at)} - {formatDate(window.ends_at)}
        </p>
        {window.disable_failure_reason ? (
          <p className="mt-2 text-sm text-red-600">{window.disable_failure_reason}</p>
        ) : null}
      </div>
      <Badge variant={window.blocks_writes ? "secondary" : "outline"}>
        {window.blocks_writes ? "write gate" : "announcement only"}
      </Badge>
    </article>
  );
}

export function CapacityPanel({ workspaceId }: { workspaceId?: string | null }) {
  const capacityQuery = useCapacityOverview(workspaceId);
  const signals = capacityQuery.data ?? [];
  const recommendations = signals.filter((signal) => signal.recommendation);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Capacity</h3>
          <p className="text-sm text-muted-foreground">
            {signals.length > 0 ? `${signals.length} resource classes` : "Waiting for signals"}
          </p>
        </div>
        <RunbookLinks includeCost />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {signals.length === 0 ? (
          <div className="rounded-lg border border-border/70 bg-background p-4 text-sm text-muted-foreground">
            No capacity signals available.
          </div>
        ) : (
          signals.map((signal) => <CapacitySignalCard key={signal.resource_class} signal={signal} />)
        )}
      </div>

      <div className="rounded-lg border border-border/70 bg-background">
        <div className="flex items-center gap-2 border-b border-border/70 px-4 py-3">
          <Gauge className="h-4 w-4 text-muted-foreground" />
          <h4 className="font-medium">Recommendations</h4>
        </div>
        <div className="divide-y divide-border/70">
          {recommendations.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No active recommendations.</p>
          ) : (
            recommendations.map((signal) => (
              <article key={signal.resource_class} className="grid gap-3 p-4 md:grid-cols-[1fr_auto]">
                <div>
                  <p className="font-medium">{signal.recommendation?.action}</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {signal.recommendation?.reason}
                  </p>
                </div>
                {signal.recommendation?.link ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={signal.recommendation.link}>
                      <ExternalLink className="h-4 w-4" />
                      Open
                    </a>
                  </Button>
                ) : null}
              </article>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function CapacitySignalCard({ signal }: { signal: CapacitySignalResponse }) {
  const projected = numericField(signal.projection, [
    "projected_utilization",
    "utilization",
    "projected_utilization_percent",
  ]);
  const threshold = numericField(signal.saturation_horizon, ["threshold"]);
  const progressValue = projected === null ? null : projected <= 1 ? projected * 100 : projected;
  const thresholdLabel =
    threshold === null ? "No threshold" : `${Math.round((threshold <= 1 ? threshold * 100 : threshold) * 10) / 10}%`;

  return (
    <div className="rounded-lg border border-border/70 bg-background p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-medium capitalize">{signal.resource_class.replaceAll("_", " ")}</p>
        <Badge variant={signal.confidence === "ok" ? "secondary" : "outline"}>
          {signal.confidence.replaceAll("_", " ")}
        </Badge>
      </div>
      <div className="mt-4 space-y-2">
        <div className="flex justify-between text-sm text-muted-foreground">
          <span>Projection</span>
          <span>{progressValue === null ? "No sample" : `${Math.round(progressValue)}%`}</span>
        </div>
        <Progress value={progressValue ?? 0} />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Threshold {thresholdLabel} · generated {formatDate(signal.generated_at)}
      </p>
    </div>
  );
}
