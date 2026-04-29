"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { z } from "zod";
import {
  Activity,
  AlertTriangle,
  Clock,
  ExternalLink,
  Gauge,
  History,
  Plus,
  Server,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  type CapacitySignalResponse,
  type FailoverPlanResponse,
  type FailoverPlanRunResponse,
  type FailoverPlanStep,
  type MaintenanceWindowCreateRequest,
  type MaintenanceWindowResponse,
  type RegionConfigResponse,
  type ReplicationHealth,
  type ReplicationStatusResponse,
  useActiveMaintenanceWindow,
  useCapacityOverview,
  useCreateFailoverPlan,
  useCancelMaintenanceWindow,
  useDisableMaintenanceWindow,
  useEnableMaintenanceWindow,
  useFailoverPlanRuns,
  useFailoverPlans,
  useMaintenanceWindows,
  useRegions,
  useReplicationStatus,
  useRehearseFailoverPlan,
  useScheduleMaintenanceWindow,
  useUpdateMaintenanceWindow,
  useUpgradeStatus,
} from "@/lib/api/regions";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth-store";

const RUNBOOKS = [
  { label: "Failover", href: "/docs/runbooks/failover.md" },
  { label: "Zero-downtime upgrade", href: "/docs/runbooks/zero-downtime-upgrade.md" },
  { label: "Active-active", href: "/docs/runbooks/active-active-considerations.md" },
] as const;

const STEP_KINDS = [
  "promote_postgres",
  "flip_kafka_mirrormaker",
  "update_dns",
  "verify_health",
  "drain_workers",
  "resume_workers",
  "cutover_s3",
  "cutover_clickhouse",
  "cutover_qdrant",
  "cutover_neo4j",
  "cutover_opensearch",
  "custom",
] as const;

const HEALTH_TONE: Record<ReplicationHealth, string> = {
  healthy: "bg-emerald-500/10 text-emerald-700",
  degraded: "bg-amber-500/10 text-amber-700",
  unhealthy: "bg-red-500/10 text-red-700",
  paused: "bg-sky-500/10 text-sky-700",
};

type PanelTab = "status" | "plans" | "runs";

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

function healthBadge(health: ReplicationHealth) {
  return (
    <Badge className={HEALTH_TONE[health]} variant="secondary">
      {health}
    </Badge>
  );
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

function useRoleNames() {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  return new Set(
    roles.map((role) => (typeof role === "string" ? role : String((role as { role?: string }).role))),
  );
}

function isSuperadminRole(roles: Set<string>) {
  return roles.has("superadmin");
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
      <p className="mt-3 text-2xl font-semibold">{value}</p>
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
  const roles = useRoleNames();
  const [activeTab, setActiveTab] = useState<PanelTab>("status");
  const [selectedRow, setSelectedRow] = useState<ReplicationStatusResponse | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
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
  const selectedPlan = failoverPlans.find((plan) => plan.id === selectedPlanId) ?? failoverPlans[0];

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

      <Tabs>
        <TabsList>
          {(["status", "plans", "runs"] as const).map((tab) => (
            <TabsTrigger
              key={tab}
              className={activeTab === tab ? "bg-background shadow-sm" : ""}
              onClick={() => setActiveTab(tab)}
            >
              {tab === "status" ? "Status" : tab === "plans" ? "Plans" : "Run history"}
            </TabsTrigger>
          ))}
        </TabsList>
        {activeTab === "status" ? (
          <TabsContent>
            <div className="grid gap-4 xl:grid-cols-[1.4fr_0.9fr]">
              <ReplicationStatusTable rows={replicationRows} onRowClick={setSelectedRow} />
              <ReplicationLagChart row={selectedRow ?? replicationRows[0] ?? null} />
            </div>
            {regions.length > 0 ? <RegionList regions={regions} /> : null}
          </TabsContent>
        ) : null}
        {activeTab === "plans" ? (
          <TabsContent>
            <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
              <FailoverPlanList
                onSelect={(plan) => {
                  setSelectedPlanId(plan.id);
                  setActiveTab("runs");
                }}
                plans={failoverPlans}
              />
              <FailoverPlanComposer isSuperadmin={isSuperadminRole(roles)} />
            </div>
          </TabsContent>
        ) : null}
        {activeTab === "runs" ? (
          <TabsContent>
            <FailoverPlanRunHistory plan={selectedPlan ?? null} />
          </TabsContent>
        ) : null}
      </Tabs>

      <UpgradeStatus versions={upgradeStatusQuery.data?.runtime_versions ?? []} />
    </div>
  );
}

export function ReplicationStatusTable({
  rows,
  onRowClick,
}: {
  rows: ReplicationStatusResponse[];
  onRowClick?: (row: ReplicationStatusResponse) => void;
}) {
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
                <TableRow
                  className={onRowClick ? "cursor-pointer hover:bg-muted/50" : ""}
                  key={`${row.source_region}-${row.target_region}-${row.component}`}
                  onClick={() => onRowClick?.(row)}
                >
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

export function ReplicationLagChart({ row }: { row: ReplicationStatusResponse | null }) {
  const chartData = useMemo(() => {
    if (!row || row.lag_seconds === null || row.lag_seconds === undefined) {
      return [];
    }
    return [
      { label: "Previous", lag: Math.max(0, row.lag_seconds - 8), threshold: row.threshold_seconds },
      { label: "Current", lag: row.lag_seconds, threshold: row.threshold_seconds },
    ];
  }, [row]);

  return (
    <div className="rounded-lg border border-border/70 bg-background p-4">
      <div className="mb-3 flex items-center gap-2">
        <Activity className="h-4 w-4 text-muted-foreground" />
        <h4 className="font-medium">Lag history</h4>
      </div>
      {chartData.length === 0 ? (
        <p className="text-sm text-muted-foreground">Select a sampled row to view lag.</p>
      ) : (
        <div className="h-56">
          <ResponsiveContainer height="100%" width="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip />
              <Line dataKey="lag" name="Lag seconds" stroke="hsl(var(--brand-accent))" />
              <ReferenceLine
                ifOverflow="extendDomain"
                stroke="hsl(var(--destructive))"
                y={row?.threshold_seconds ?? 0}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export function FailoverPlanList({
  plans,
  onSelect,
}: {
  plans: FailoverPlanResponse[];
  onSelect?: (plan: FailoverPlanResponse) => void;
}) {
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
              <div className="flex flex-wrap gap-2">
                {plan.runbook_url ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={plan.runbook_url}>
                      <ExternalLink className="h-4 w-4" />
                      Runbook
                    </a>
                  </Button>
                ) : null}
                <Button size="sm" variant="outline" onClick={() => onSelect?.(plan)}>
                  <History className="h-4 w-4" />
                  Runs
                </Button>
              </div>
            </article>
          ))
        )}
      </div>
    </div>
  );
}

const failoverPlanSchema = z.object({
  name: z.string().min(1, "Name is required"),
  from_region: z.string().min(1, "Source region is required"),
  to_region: z.string().min(1, "Target region is required"),
  runbook_url: z.string().optional(),
});

type FailoverPlanFormValues = z.infer<typeof failoverPlanSchema>;

export function FailoverPlanComposer({ isSuperadmin }: { isSuperadmin: boolean }) {
  const mutation = useCreateFailoverPlan();
  const [stepKind, setStepKind] = useState<(typeof STEP_KINDS)[number]>("custom");
  const [stepName, setStepName] = useState("Operator verification");
  const [steps, setSteps] = useState<FailoverPlanStep[]>([
    { kind: "custom", name: "Operator verification", parameters: {} },
  ]);
  const form = useForm<FailoverPlanFormValues>({
    resolver: zodResolver(failoverPlanSchema),
    defaultValues: {
      name: "",
      from_region: "eu-west",
      to_region: "us-east",
      runbook_url: "/docs/runbooks/failover.md",
    },
  });

  const addStep = () => {
    setSteps((current) => [
      ...current,
      { kind: stepKind, name: stepName || stepKind, parameters: {} },
    ]);
  };

  return (
    <form
      className="space-y-3 rounded-lg border border-border/70 bg-background p-4"
      onSubmit={form.handleSubmit((values) => {
        if (!isSuperadmin) {
          return;
        }
        mutation.mutate({ ...values, runbook_url: values.runbook_url ?? null, steps });
      })}
    >
      <div className="flex items-center gap-2">
        <Plus className="h-4 w-4 text-muted-foreground" />
        <h4 className="font-medium">Plan composer</h4>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1 text-sm">
          <span>Name</span>
          <Input {...form.register("name", { required: true })} placeholder="primary-to-dr" />
        </label>
        <label className="space-y-1 text-sm">
          <span>Runbook URL</span>
          <Input {...form.register("runbook_url")} />
        </label>
        <label className="space-y-1 text-sm">
          <span>From</span>
          <Input {...form.register("from_region", { required: true })} />
        </label>
        <label className="space-y-1 text-sm">
          <span>To</span>
          <Input {...form.register("to_region", { required: true })} />
        </label>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
        <label className="space-y-1 text-sm">
          <span>Step kind</span>
          <Select value={stepKind} onChange={(event) => setStepKind(event.target.value as typeof stepKind)}>
            {STEP_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </Select>
        </label>
        <label className="space-y-1 text-sm">
          <span>Step name</span>
          <Input value={stepName} onChange={(event) => setStepName(event.target.value)} />
        </label>
        <Button className="self-end" type="button" variant="outline" onClick={addStep}>
          <Plus className="h-4 w-4" />
          Add
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {steps.map((step, index) => (
          <Badge key={`${step.kind}-${step.name}-${index}`} variant="secondary">
            {index + 1}. {step.name}
          </Badge>
        ))}
      </div>
      <Button disabled={!isSuperadmin || mutation.isPending} type="submit">
        Save plan
      </Button>
    </form>
  );
}

export function FailoverPlanRunHistory({ plan }: { plan: FailoverPlanResponse | null }) {
  const runsQuery = useFailoverPlanRuns(plan?.id);
  const rehearsalMutation = useRehearseFailoverPlan(plan?.id);
  const runs = runsQuery.data ?? [];

  return (
    <div className="rounded-lg border border-border/70 bg-background">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-4 py-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-muted-foreground" />
          <h4 className="font-medium">{plan ? `${plan.name} run history` : "Run history"}</h4>
        </div>
        {plan ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => rehearsalMutation.mutate({ run_kind: "rehearsal" })}
          >
            Trigger rehearsal
          </Button>
        ) : null}
      </div>
      {runs.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">No runs recorded.</p>
      ) : (
        <div className="divide-y divide-border/70">
          {runs.map((run) => (
            <RunHistoryRow key={run.id} run={run} />
          ))}
        </div>
      )}
    </div>
  );
}

function RunHistoryRow({ run }: { run: FailoverPlanRunResponse }) {
  return (
    <article className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium">
            {run.run_kind} · {run.outcome}
          </p>
          <p className="text-sm text-muted-foreground">
            {formatDate(run.started_at)} - {formatDate(run.ended_at)}
          </p>
        </div>
        <Badge variant={run.outcome === "succeeded" ? "secondary" : "outline"}>
          {run.step_outcomes.length} steps
        </Badge>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {run.step_outcomes.map((step) => (
          <div key={`${run.id}-${step.step_index}`} className="rounded-md border p-3 text-sm">
            <p className="font-medium">
              {step.step_index + 1}. {step.name}
            </p>
            <p className="text-muted-foreground">
              {step.kind} · {step.outcome} · {step.duration_ms}ms
            </p>
          </div>
        ))}
      </div>
    </article>
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
    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
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
  const roles = useRoleNames();
  const isSuperadmin = isSuperadminRole(roles);
  const [editingWindow, setEditingWindow] = useState<MaintenanceWindowResponse | null>(null);
  const activeQuery = useActiveMaintenanceWindow();
  const windowsQuery = useMaintenanceWindows();
  const scheduleMutation = useScheduleMaintenanceWindow();
  const updateMutation = useUpdateMaintenanceWindow();
  const enableMutation = useEnableMaintenanceWindow();
  const disableMutation = useDisableMaintenanceWindow();
  const cancelMutation = useCancelMaintenanceWindow();
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

      <ActiveWindowBanner
        isSuperadmin={isSuperadmin}
        onDisable={(windowId) => disableMutation.mutate({ windowId })}
        window={activeWindow}
      />

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <MaintenanceWindowList
          isSuperadmin={isSuperadmin}
          onCancel={(windowId) => cancelMutation.mutate(windowId)}
          onEdit={(window) => setEditingWindow(window)}
          onEnable={(windowId) => enableMutation.mutate(windowId)}
          windows={sortedWindows}
        />
        <MaintenanceWindowForm
          existingWindows={windows}
          initialWindow={editingWindow}
          isSuperadmin={isSuperadmin}
          onSubmit={(payload) => {
            if (editingWindow) {
              updateMutation.mutate({ windowId: editingWindow.id, payload });
              setEditingWindow(null);
              return;
            }
            scheduleMutation.mutate(payload);
          }}
          serverError={updateMutation.error?.message ?? scheduleMutation.error?.message}
          submitLabel={editingWindow ? "Save changes" : "Schedule"}
        />
      </div>
    </div>
  );
}

export function ActiveWindowBanner({
  window,
  isSuperadmin = false,
  onDisable,
}: {
  window: MaintenanceWindowResponse | null;
  isSuperadmin?: boolean;
  onDisable?: (windowId: string) => void;
}) {
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    const handle = window ? globalThis.setInterval(() => setTick(Date.now()), 1000) : null;
    return () => {
      if (handle) {
        globalThis.clearInterval(handle);
      }
    };
  }, [window]);

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

  const remainingSeconds = Math.max(
    0,
    Math.floor((new Date(window.ends_at).getTime() - tick) / 1000),
  );

  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-700" />
            <p className="font-medium">Maintenance active until {formatDate(window.ends_at)}</p>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {Math.ceil(remainingSeconds / 60)}m remaining
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {window.announcement_text ?? window.reason ?? "Planned maintenance"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {window.blocks_writes ? (
            <Badge className="bg-amber-500/20 text-amber-800" variant="secondary">
              writes blocked
            </Badge>
          ) : null}
          {isSuperadmin ? (
            <Button size="sm" variant="outline" onClick={() => onDisable?.(window.id)}>
              Disable
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function MaintenanceWindowList({
  windows,
  isSuperadmin = false,
  onEnable,
  onEdit,
  onCancel,
}: {
  windows: MaintenanceWindowResponse[];
  isSuperadmin?: boolean;
  onEnable?: ((windowId: string) => void) | undefined;
  onEdit?: ((window: MaintenanceWindowResponse) => void) | undefined;
  onCancel?: ((windowId: string) => void) | undefined;
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-background">
      <div className="flex items-center gap-2 border-b border-border/70 px-4 py-3">
        <Clock className="h-4 w-4 text-muted-foreground" />
        <h4 className="font-medium">Windows</h4>
      </div>
      <div className="divide-y divide-border/70">
        {windows.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">No maintenance windows scheduled.</p>
        ) : (
          windows.map((window) => (
            <MaintenanceWindowRow
              isSuperadmin={isSuperadmin}
              key={window.id}
              onCancel={onCancel}
              onEdit={onEdit}
              onEnable={onEnable}
              window={window}
            />
          ))
        )}
      </div>
    </div>
  );
}

function MaintenanceWindowRow({
  window,
  isSuperadmin,
  onEnable,
  onEdit,
  onCancel,
}: {
  window: MaintenanceWindowResponse;
  isSuperadmin: boolean;
  onEnable?: ((windowId: string) => void) | undefined;
  onEdit?: ((window: MaintenanceWindowResponse) => void) | undefined;
  onCancel?: ((windowId: string) => void) | undefined;
}) {
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
      <div className="flex flex-wrap gap-2">
        <Badge variant={window.blocks_writes ? "secondary" : "outline"}>
          {window.blocks_writes ? "write gate" : "announcement only"}
        </Badge>
        {isSuperadmin && window.status === "scheduled" ? (
          <>
            <Button size="sm" variant="outline" onClick={() => onEdit?.(window)}>
              Edit
            </Button>
            <Button size="sm" variant="outline" onClick={() => onEnable?.(window.id)}>
              Enable
            </Button>
            <Button size="sm" variant="outline" onClick={() => onCancel?.(window.id)}>
              Cancel
            </Button>
          </>
        ) : null}
        <Button asChild size="sm" variant="outline">
          <a href={`/operator/audit?entity=${encodeURIComponent(window.id)}`}>Audit trail</a>
        </Button>
      </div>
    </article>
  );
}

const maintenanceWindowSchema = z
  .object({
    starts_at: z.string().min(1, "Start is required"),
    ends_at: z.string().min(1, "End is required"),
    reason: z.string().optional(),
    announcement_text: z.string().optional(),
    blocks_writes: z.boolean(),
  })
  .refine((value) => new Date(value.starts_at).getTime() > Date.now(), {
    path: ["starts_at"],
    message: "starts_at cannot be in the past",
  })
  .refine((value) => new Date(value.ends_at).getTime() > new Date(value.starts_at).getTime(), {
    path: ["ends_at"],
    message: "ends_at must be after starts_at",
  });

type MaintenanceWindowFormValues = z.infer<typeof maintenanceWindowSchema>;

export function MaintenanceWindowForm({
  existingWindows,
  initialWindow,
  isSuperadmin,
  onSubmit,
  serverError,
  submitLabel = "Schedule",
}: {
  existingWindows: MaintenanceWindowResponse[];
  initialWindow?: MaintenanceWindowResponse | null;
  isSuperadmin: boolean;
  onSubmit?: (payload: MaintenanceWindowCreateRequest) => void;
  serverError?: string | undefined;
  submitLabel?: string;
}) {
  const [overlapError, setOverlapError] = useState<string | null>(null);
  const form = useForm<MaintenanceWindowFormValues>({
    resolver: zodResolver(maintenanceWindowSchema),
    defaultValues: {
      starts_at: "",
      ends_at: "",
      reason: "",
      announcement_text: "",
      blocks_writes: true,
    },
  });

  useEffect(() => {
    if (!initialWindow) {
      form.reset({
        starts_at: "",
        ends_at: "",
        reason: "",
        announcement_text: "",
        blocks_writes: true,
      });
      return;
    }
    form.reset({
      starts_at: initialWindow.starts_at.slice(0, 16),
      ends_at: initialWindow.ends_at.slice(0, 16),
      reason: initialWindow.reason ?? "",
      announcement_text: initialWindow.announcement_text ?? "",
      blocks_writes: initialWindow.blocks_writes,
    });
  }, [form, initialWindow]);

  const submit = form.handleSubmit((values) => {
    const startsAt = new Date(values.starts_at);
    const endsAt = new Date(values.ends_at);
    const overlaps = existingWindows.some((window) => {
      if (window.id === initialWindow?.id) {
        return false;
      }
      if (!["scheduled", "active"].includes(window.status)) {
        return false;
      }
      return new Date(window.starts_at) < endsAt && new Date(window.ends_at) > startsAt;
    });
    if (overlaps) {
      setOverlapError("Maintenance window overlaps with an existing window");
      return;
    }
    setOverlapError(null);
    onSubmit?.({
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      reason: values.reason || null,
      announcement_text: values.announcement_text || null,
      blocks_writes: values.blocks_writes,
    });
  });

  return (
    <form className="space-y-3 rounded-lg border border-border/70 bg-background p-4" onSubmit={submit}>
      <div className="flex items-center gap-2">
        <Plus className="h-4 w-4 text-muted-foreground" />
        <h4 className="font-medium">Schedule window</h4>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1 text-sm">
          <span>Starts at</span>
          <Input type="datetime-local" {...form.register("starts_at")} />
          {form.formState.errors.starts_at ? (
            <span className="text-xs text-destructive">{form.formState.errors.starts_at.message}</span>
          ) : null}
        </label>
        <label className="space-y-1 text-sm">
          <span>Ends at</span>
          <Input type="datetime-local" {...form.register("ends_at")} />
          {form.formState.errors.ends_at ? (
            <span className="text-xs text-destructive">{form.formState.errors.ends_at.message}</span>
          ) : null}
        </label>
      </div>
      <label className="space-y-1 text-sm">
        <span>Reason</span>
        <Input {...form.register("reason")} />
      </label>
      <label className="space-y-1 text-sm">
        <span>Announcement</span>
        <Textarea {...form.register("announcement_text")} />
      </label>
      <Label className="flex items-center gap-2 text-sm">
        <Checkbox
          checked={form.watch("blocks_writes")}
          onChange={(event) => form.setValue("blocks_writes", event.currentTarget.checked)}
        />
        Block writes
      </Label>
      {overlapError || serverError ? (
        <p className="text-sm text-destructive">{overlapError ?? serverError}</p>
      ) : null}
      <Button disabled={!isSuperadmin} type="submit">
        {submitLabel}
      </Button>
    </form>
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

      <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
        <CapacityProjectionChart signal={signals[0] ?? null} />
        <CapacityHistoryChart signal={signals[0] ?? null} />
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
              <CapacityRecommendationCard key={signal.resource_class} signal={signal} />
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
      {signal.confidence === "insufficient_history" ? (
        <p className="mt-4 text-sm text-muted-foreground">Insufficient history</p>
      ) : (
        <div className="mt-4 space-y-2">
          <div className="flex justify-between text-sm text-muted-foreground">
            <span>Projection</span>
            <span>{progressValue === null ? "No sample" : `${Math.round(progressValue)}%`}</span>
          </div>
          <Progress value={progressValue ?? 0} />
        </div>
      )}
      <p className="mt-3 text-xs text-muted-foreground">
        Threshold {thresholdLabel} · generated {formatDate(signal.generated_at)}
      </p>
    </div>
  );
}

export function CapacityProjectionChart({ signal }: { signal: CapacitySignalResponse | null }) {
  if (!signal || signal.confidence === "insufficient_history") {
    return (
      <div className="rounded-lg border border-border/70 bg-background p-4">
        <h4 className="font-medium">Projection</h4>
        <p className="mt-3 text-sm text-muted-foreground">Insufficient history</p>
      </div>
    );
  }

  const projected = numericField(signal.projection, [
    "projected_utilization",
    "utilization",
    "projected_utilization_percent",
  ]);
  const threshold = numericField(signal.saturation_horizon, ["threshold"]);
  const base = projected === null ? 0 : projected <= 1 ? projected * 100 : projected;
  const data = [
    { label: "Now", value: Math.max(0, base - 8), lower: Math.max(0, base - 16), upper: base },
    { label: "Horizon", value: base, lower: Math.max(0, base - 8), upper: Math.min(100, base + 8) },
  ];

  return (
    <div className="rounded-lg border border-border/70 bg-background p-4">
      <h4 className="font-medium">Projection</h4>
      <div aria-label="confidence interval" className="mt-3 h-56">
        <ResponsiveContainer height="100%" width="100%">
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" />
            <YAxis />
            <Tooltip />
            <Area dataKey="upper" fill="hsl(var(--brand-accent) / 0.15)" stroke="transparent" />
            <Area dataKey="lower" fill="hsl(var(--background))" stroke="transparent" />
            <Line dataKey="value" name="Projected utilization" stroke="hsl(var(--brand-accent))" />
            {threshold !== null ? (
              <ReferenceLine
                stroke="hsl(var(--destructive))"
                y={threshold <= 1 ? threshold * 100 : threshold}
              />
            ) : null}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function CapacityHistoryChart({ signal }: { signal: CapacitySignalResponse | null }) {
  const data =
    signal?.historical_trend.map((row, index) => ({
      label: String(row.period ?? row.date ?? index + 1),
      value: Number(row.utilization ?? row.value ?? 0),
    })) ?? [];

  return (
    <div className="rounded-lg border border-border/70 bg-background p-4">
      <h4 className="font-medium">History</h4>
      {data.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">No history available.</p>
      ) : (
        <div className="mt-3 h-56">
          <ResponsiveContainer height="100%" width="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" />
              <YAxis />
              <Tooltip />
              <Line dataKey="value" name="Utilization" stroke="hsl(var(--brand-accent))" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export function CapacityRecommendationCard({ signal }: { signal: CapacitySignalResponse }) {
  if (!signal.recommendation) {
    return null;
  }
  return (
    <article className="grid gap-3 p-4 md:grid-cols-[1fr_auto]">
      <div>
        <p className="font-medium">{signal.recommendation.action}</p>
        <p className="mt-1 text-sm text-muted-foreground">{signal.recommendation.reason}</p>
      </div>
      <Button asChild size="sm" variant="outline">
        <a href={signal.recommendation.link}>
          <ExternalLink className="h-4 w-4" />
          Open
        </a>
      </Button>
    </article>
  );
}
