"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  AlertTriangle,
  Bell,
  Check,
  Clipboard,
  ExternalLink,
  FileText,
  GitBranch,
  RefreshCcw,
  Send,
} from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { StaleDataAlert } from "@/components/features/admin/shared/StaleDataAlert";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import type {
  ExternalAlertResponse,
  IncidentDetailResponse,
  IncidentResponse,
  IntegrationCreateRequest,
  IntegrationResponse,
  PostMortemResponse,
  RunbookResponse,
  RunbookUpdateRequest,
  TimelineEntry,
  TimelineSourceCoverage,
} from "@/lib/api/incidents";

const severityTone: Record<string, string> = {
  critical: "bg-red-600 text-white",
  high: "bg-orange-500 text-white",
  warning: "bg-amber-500 text-black",
  info: "bg-sky-600 text-white",
};

const sourceTone: Record<string, string> = {
  audit_chain: "bg-purple-600 text-white",
  execution_journal: "bg-blue-600 text-white",
  kafka: "bg-emerald-600 text-white",
};

export const runbookEditorSchema = z.object({
  expected_version: z.number().int().min(1),
  title: z.string().min(1),
  symptoms: z.string().min(1),
  diagnostic_commands: z
    .array(z.object({ command: z.string().min(1), description: z.string().min(1) }))
    .min(1),
  remediation_steps: z.string().min(1),
  escalation_path: z.string().min(1),
  status: z.enum(["active", "retired"]),
});

export const integrationConfigSchema = z.object({
  provider: z.enum(["pagerduty", "opsgenie", "victorops"]),
  integration_key_ref: z.string().regex(/^incident-response\/integrations\/[\w.-]+$/),
  enabled: z.boolean(),
  critical: z.string().min(1),
  high: z.string().min(1),
  warning: z.string().min(1),
  info: z.string().min(1),
});

type RunbookFormValues = z.infer<typeof runbookEditorSchema>;
type IntegrationFormValues = z.infer<typeof integrationConfigSchema>;

export function IncidentTable({
  incidents,
  isLoading,
  statusFilter,
  severityFilter,
  onStatusFilterChange,
  onSeverityFilterChange,
  onRowClick,
}: {
  incidents: IncidentResponse[];
  isLoading?: boolean;
  statusFilter: string;
  severityFilter: string;
  onStatusFilterChange: (value: string) => void;
  onSeverityFilterChange: (value: string) => void;
  onRowClick: (incident: IncidentResponse) => void;
}) {
  return (
    <Card>
      <CardHeader className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Bell className="h-4 w-4" />
            Incidents
          </CardTitle>
          <div className="grid w-full gap-2 sm:w-auto sm:grid-cols-2">
            <Select
              aria-label="Incident status filter"
              value={statusFilter}
              onChange={(event) => onStatusFilterChange(event.target.value)}
            >
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="resolved">Resolved</option>
              <option value="">All statuses</option>
            </Select>
            <Select
              aria-label="Incident severity filter"
              value={severityFilter}
              onChange={(event) => onSeverityFilterChange(event.target.value)}
            >
              <option value="">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="warning">Warning</option>
              <option value="info">Info</option>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? <p className="text-sm text-muted-foreground">Loading incidents...</p> : null}
        {!isLoading && incidents.length === 0 ? (
          <EmptyState title="No incidents" description="The current filters have no matching incidents." />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Severity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Triggered</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {incidents.map((incident) => (
                <TableRow
                  key={incident.id}
                  className="cursor-pointer"
                  onClick={() => onRowClick(incident)}
                >
                  <TableCell>
                    <Badge className={severityTone[incident.severity]}>{incident.severity}</Badge>
                  </TableCell>
                  <TableCell>{incident.status}</TableCell>
                  <TableCell className="font-medium">{incident.title}</TableCell>
                  <TableCell>{formatDate(incident.triggered_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export function IncidentDetail({
  incident,
  onResolve,
  onStartPostMortem,
  isResolving,
}: {
  incident: IncidentDetailResponse;
  onResolve: () => void;
  onStartPostMortem: () => void;
  isResolving?: boolean;
}) {
  const canStartPostMortem = incident.status === "resolved" || incident.status === "auto_resolved";
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-xl">{incident.title}</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">{incident.description}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Badge className={severityTone[incident.severity]}>{incident.severity}</Badge>
              <Badge variant="outline">{incident.status}</Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {incident.related_executions.map((executionId) => (
              <Button key={executionId} asChild size="sm" variant="outline">
                <Link href={`/operator/executions/${executionId}`}>
                  <GitBranch className="h-4 w-4" />
                  {shortId(executionId)}
                </Link>
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button disabled={isResolving || canStartPostMortem} onClick={onResolve}>
              <Check className="h-4 w-4" />
              Resolve
            </Button>
            <Button disabled={!canStartPostMortem} variant="outline" onClick={onStartPostMortem}>
              <FileText className="h-4 w-4" />
              Start post-mortem
            </Button>
          </div>
        </CardContent>
      </Card>

      <RunbookViewer
        authoringLink={incident.runbook_authoring_link ?? undefined}
        runbook={incident.runbook ?? null}
        unmapped={incident.runbook_scenario_unmapped}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">External delivery</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          {incident.external_alerts.length ? (
            incident.external_alerts.map((alert) => (
              <ExternalDeliveryStatus key={alert.id} alert={alert} />
            ))
          ) : (
            <p className="text-sm text-muted-foreground">No external page attempted.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function ExternalDeliveryStatus({ alert }: { alert: ExternalAlertResponse }) {
  return (
    <div className="rounded-md border p-3">
      <div className="flex items-center justify-between gap-3">
        <Badge variant={alert.delivery_status === "failed" ? "destructive" : "outline"}>
          {alert.delivery_status}
        </Badge>
        <span className="text-xs text-muted-foreground">Attempts {alert.attempt_count}</span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {alert.provider_reference ?? alert.last_error ?? alert.next_retry_at ?? alert.integration_id}
      </p>
    </div>
  );
}

export function RunbookViewer({
  runbook,
  authoringLink,
  unmapped,
}: {
  runbook?: RunbookResponse | null;
  authoringLink?: string | undefined;
  unmapped?: boolean;
}) {
  if (!runbook) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Runbook</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {unmapped ? "No runbook scenario mapped." : "No runbook for this scenario."}
          </p>
          {authoringLink ? (
            <Button asChild variant="outline">
              <Link href={authoringLink}>
                <ExternalLink className="h-4 w-4" />
                Author runbook
              </Link>
            </Button>
          ) : null}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-base">{runbook.title}</CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">{runbook.scenario}</p>
        </div>
        <RunbookStaleBadge isStale={runbook.is_stale} />
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-2">
        <TextBlock title="Symptoms" value={runbook.symptoms} />
        <TextBlock title="Escalation" value={runbook.escalation_path} />
        <div className="space-y-2">
          <p className="text-sm font-medium">Diagnostic commands</p>
          {runbook.diagnostic_commands.map((command) => (
            <CommandCopy key={`${command.command}-${command.description}`} command={command.command} description={command.description} />
          ))}
        </div>
        <TextBlock title="Remediation" value={runbook.remediation_steps} />
      </CardContent>
    </Card>
  );
}

export function RunbookEditor({
  runbook,
  onSubmit,
  isSaving,
  staleVersion,
  onReload,
}: {
  runbook: RunbookResponse;
  onSubmit: (payload: RunbookUpdateRequest) => void;
  isSaving?: boolean;
  staleVersion?: number | null;
  onReload?: () => void;
}) {
  const form = useForm<RunbookFormValues>({
    resolver: zodResolver(runbookEditorSchema),
    defaultValues: {
      expected_version: runbook.version,
      title: runbook.title,
      symptoms: runbook.symptoms,
      diagnostic_commands: runbook.diagnostic_commands.length
        ? runbook.diagnostic_commands
        : [{ command: "", description: "" }],
      remediation_steps: runbook.remediation_steps,
      escalation_path: runbook.escalation_path,
      status: runbook.status,
    },
  });

  return (
    <form
      className="space-y-4"
      onSubmit={form.handleSubmit((values) => onSubmit(values))}
    >
      {staleVersion ? <StaleDataAlert onReload={onReload ?? (() => window.location.reload())} /> : null}
      <Input aria-label="Runbook title" {...form.register("title")} />
      <Textarea aria-label="Symptoms" {...form.register("symptoms")} />
      <div className="grid gap-3 md:grid-cols-2">
        <Input aria-label="Diagnostic command" {...form.register("diagnostic_commands.0.command")} />
        <Input aria-label="Diagnostic description" {...form.register("diagnostic_commands.0.description")} />
      </div>
      <Textarea aria-label="Remediation steps" {...form.register("remediation_steps")} />
      <Textarea aria-label="Escalation path" {...form.register("escalation_path")} />
      <Select aria-label="Runbook status" {...form.register("status")}>
        <option value="active">Active</option>
        <option value="retired">Retired</option>
      </Select>
      <Button disabled={isSaving} type="submit">
        <Check className="h-4 w-4" />
        Save
      </Button>
    </form>
  );
}

export function RunbookStaleBadge({ isStale }: { isStale: boolean }) {
  return isStale ? (
    <Badge className="bg-amber-500 text-black">Stale</Badge>
  ) : (
    <Badge variant="outline">Fresh</Badge>
  );
}

export function IntegrationConfigForm({
  integration,
  onSubmit,
  isSaving,
}: {
  integration?: IntegrationResponse | null;
  onSubmit: (payload: IntegrationCreateRequest) => void;
  isSaving?: boolean;
}) {
  const mapping = integration?.alert_severity_mapping ?? {};
  const form = useForm<IntegrationFormValues>({
    resolver: zodResolver(integrationConfigSchema),
    defaultValues: {
      provider: integration?.provider ?? "pagerduty",
      integration_key_ref: integration?.integration_key_ref ?? "incident-response/integrations/",
      enabled: integration?.enabled ?? true,
      critical: mapping.critical ?? "P1",
      high: mapping.high ?? "P2",
      warning: mapping.warning ?? "P3",
      info: mapping.info ?? "P5",
    },
  });
  return (
    <form
      className="space-y-4"
      onSubmit={form.handleSubmit((values) =>
        onSubmit({
          provider: values.provider,
          integration_key_ref: values.integration_key_ref,
          enabled: values.enabled,
          alert_severity_mapping: {
            critical: values.critical,
            high: values.high,
            warning: values.warning,
            info: values.info,
          },
        }),
      )}
    >
      <Select aria-label="Provider" {...form.register("provider")}>
        <option value="pagerduty">PagerDuty</option>
        <option value="opsgenie">OpsGenie</option>
        <option value="victorops">VictorOps</option>
      </Select>
      <Input aria-label="Vault path" {...form.register("integration_key_ref")} />
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" {...form.register("enabled")} />
        Enabled
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        {(["critical", "high", "warning", "info"] as const).map((field) => (
          <Input key={field} aria-label={`${field} mapping`} {...form.register(field)} />
        ))}
      </div>
      <Button disabled={isSaving} type="submit">
        <Check className="h-4 w-4" />
        Save
      </Button>
    </form>
  );
}

export function PostMortemComposer({
  postMortem,
  onSaveSections,
  onMarkBlameless,
  onDistribute,
}: {
  postMortem: PostMortemResponse;
  onSaveSections: (payload: { impact_assessment: string; root_cause: string; action_items: unknown[] }) => void;
  onMarkBlameless: () => void;
  onDistribute: (recipients: string[]) => void;
}) {
  const [impact, setImpact] = useState(postMortem.impact_assessment ?? "");
  const [rootCause, setRootCause] = useState(postMortem.root_cause ?? "");
  const [actionItems, setActionItems] = useState(JSON.stringify(postMortem.action_items ?? [], null, 2));
  const [recipients, setRecipients] = useState("");
  const parsedActions = useMemo(() => parseActionItems(actionItems), [actionItems]);
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(320px,0.9fr)_minmax(0,1.1fr)]">
      <div className="space-y-4">
        <TimelineSourceCoverageBanner coverage={postMortem.timeline_source_coverage} />
        <TimelineDisplay entries={postMortem.timeline ?? []} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Post-mortem composer</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea aria-label="Impact assessment" value={impact} onChange={(event) => setImpact(event.target.value)} />
          <Textarea aria-label="Root cause" value={rootCause} onChange={(event) => setRootCause(event.target.value)} />
          <Textarea aria-label="Action items" value={actionItems} onChange={(event) => setActionItems(event.target.value)} />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => onSaveSections({ impact_assessment: impact, root_cause: rootCause, action_items: parsedActions })}>
              <Check className="h-4 w-4" />
              Save sections
            </Button>
            <Button variant="outline" onClick={onMarkBlameless}>
              <RefreshCcw className="h-4 w-4" />
              Mark blameless
            </Button>
          </div>
          <div className="flex gap-2">
            <Input aria-label="Distribution recipients" value={recipients} onChange={(event) => setRecipients(event.target.value)} />
            <Button variant="outline" onClick={() => onDistribute(splitRecipients(recipients))}>
              <Send className="h-4 w-4" />
              Distribute
            </Button>
          </div>
          {postMortem.distribution_list?.length ? (
            <div className="space-y-1 text-sm">
              {postMortem.distribution_list.map((item) => (
                <p key={`${item.recipient}-${item.outcome}`}>
                  {item.recipient}: {item.outcome}
                </p>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

export function TimelineDisplay({ entries }: { entries: TimelineEntry[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Timeline</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {entries.length ? (
          entries.map((entry) => (
            <div key={entry.id} className="rounded-md border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className={sourceTone[entry.source]}>{entry.source}</Badge>
                <span className="text-xs text-muted-foreground">{formatDate(entry.timestamp)}</span>
              </div>
              <p className="mt-2 text-sm font-medium">{entry.summary}</p>
              {entry.event_type ? <p className="text-xs text-muted-foreground">{entry.event_type}</p> : null}
            </div>
          ))
        ) : (
          <p className="text-sm text-muted-foreground">No timeline entries.</p>
        )}
      </CardContent>
    </Card>
  );
}

export function TimelineSourceCoverageBanner({ coverage }: { coverage: TimelineSourceCoverage }) {
  const incomplete = Object.entries({
    audit_chain: coverage.audit_chain,
    execution_journal: coverage.execution_journal,
    kafka: coverage.kafka,
  }).filter(([, value]) => value !== "complete");
  if (!incomplete.length) {
    return null;
  }
  return (
    <div className="flex items-start gap-3 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
      <div>
        <p className="font-medium">Timeline source coverage is incomplete</p>
        <p className="text-muted-foreground">
          {incomplete.map(([source, value]) => `${source}: ${value}`).join(", ")}
        </p>
      </div>
    </div>
  );
}

function TextBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="space-y-1">
      <p className="text-sm font-medium">{title}</p>
      <p className="whitespace-pre-wrap text-sm text-muted-foreground">{value}</p>
    </div>
  );
}

function CommandCopy({ command, description }: { command: string; description: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="flex w-full items-center justify-between gap-3 rounded-md border p-3 text-left text-sm hover:bg-muted/50"
      type="button"
      onClick={async () => {
        await navigator.clipboard?.writeText(command);
        setCopied(true);
      }}
    >
      <span>
        <span className="block font-mono text-xs">{command}</span>
        <span className="block text-xs text-muted-foreground">{description}</span>
      </span>
      {copied ? <Check className="h-4 w-4" /> : <Clipboard className="h-4 w-4" />}
    </button>
  );
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function shortId(value: string) {
  return value.slice(0, 8);
}

function parseActionItems(value: string): unknown[] {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function splitRecipients(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
