"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export type IncidentSeverity = "critical" | "high" | "warning" | "info";
export type IncidentStatus = "open" | "acknowledged" | "resolved" | "auto_resolved";
export type PagingProvider = "pagerduty" | "opsgenie" | "victorops";
export type RunbookStatus = "active" | "retired";
export type PostMortemStatus = "draft" | "published" | "distributed";
export type TimelineSource = "audit_chain" | "execution_journal" | "kafka";
export type TimelineCoverageState = "complete" | "partial" | "unavailable";
export type DeliveryStatus = "pending" | "delivered" | "failed" | "resolved";

export interface DiagnosticCommand {
  command: string;
  description: string;
}

export interface ExternalAlertResponse {
  id: string;
  incident_id: string;
  integration_id: string;
  provider_reference?: string | null;
  delivery_status: DeliveryStatus;
  attempt_count: number;
  last_attempt_at?: string | null;
  last_error?: string | null;
  next_retry_at?: string | null;
}

export interface RunbookResponse {
  id: string;
  scenario: string;
  title: string;
  symptoms: string;
  diagnostic_commands: DiagnosticCommand[];
  remediation_steps: string;
  escalation_path: string;
  status: RunbookStatus;
  version: number;
  created_at: string;
  updated_at: string;
  updated_by?: string | null;
  is_stale: boolean;
}

export interface RunbookUpdateRequest {
  expected_version: number;
  title?: string;
  symptoms?: string;
  diagnostic_commands?: DiagnosticCommand[];
  remediation_steps?: string;
  escalation_path?: string;
  status?: RunbookStatus;
}

export type RunbookCreateRequest = Omit<
  RunbookResponse,
  "id" | "version" | "created_at" | "updated_at" | "updated_by" | "is_stale"
>;

export interface IncidentResponse {
  id: string;
  condition_fingerprint: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  title: string;
  description: string;
  triggered_at: string;
  resolved_at?: string | null;
  related_executions: string[];
  related_event_ids: string[];
  runbook_scenario?: string | null;
  alert_rule_class: string;
  post_mortem_id?: string | null;
}

export interface IncidentDetailResponse extends IncidentResponse {
  external_alerts: ExternalAlertResponse[];
  runbook?: RunbookResponse | null;
  runbook_authoring_link?: string | null;
  runbook_scenario_unmapped: boolean;
}

export interface TimelineEntry {
  id: string;
  timestamp: string;
  source: TimelineSource;
  event_type?: string | null;
  summary: string;
  topic?: string | null;
  payload_summary: Record<string, unknown>;
}

export interface TimelineSourceCoverage {
  audit_chain: TimelineCoverageState;
  execution_journal: TimelineCoverageState;
  kafka: TimelineCoverageState;
  reasons: Record<string, string>;
}

export interface PostMortemResponse {
  id: string;
  incident_id: string;
  status: PostMortemStatus;
  timeline?: TimelineEntry[] | null;
  timeline_blob_ref?: string | null;
  timeline_source_coverage: TimelineSourceCoverage;
  impact_assessment?: string | null;
  root_cause?: string | null;
  action_items?: Array<Record<string, unknown>> | null;
  distribution_list?: Array<{ recipient: string; outcome: string }> | null;
  linked_certification_ids: string[];
  blameless: boolean;
  created_at: string;
  created_by?: string | null;
  published_at?: string | null;
  distributed_at?: string | null;
}

export interface IntegrationResponse {
  id: string;
  provider: PagingProvider;
  integration_key_ref: string;
  enabled: boolean;
  alert_severity_mapping: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export interface IntegrationCreateRequest {
  provider: PagingProvider;
  integration_key_ref: string;
  alert_severity_mapping: Record<string, string>;
  enabled: boolean;
}

export interface IntegrationUpdateRequest {
  enabled?: boolean;
  alert_severity_mapping?: Record<string, string>;
}

const INCIDENTS_API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const incidentsApiClient = createApiClient(INCIDENTS_API_BASE_URL);

export const incidentQueryKeys = {
  incidents: (status?: string, severity?: string) =>
    ["incidents", status ?? "all", severity ?? "all"] as const,
  incident: (id?: string | null) => ["incidents", id ?? "none"] as const,
  runbooks: (query?: string | null) => ["runbooks", query ?? "all"] as const,
  runbook: (id?: string | null) => ["runbooks", id ?? "none"] as const,
  runbookScenario: (scenario?: string | null) => ["runbooks", "scenario", scenario ?? "none"] as const,
  postMortem: (id?: string | null) => ["post-mortems", id ?? "none"] as const,
  postMortemByIncident: (id?: string | null) => ["post-mortems", "incident", id ?? "none"] as const,
  integrations: () => ["incident-integrations"] as const,
};

function params(values: Record<string, string | undefined | null>): string {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value) {
      query.set(key, value);
    }
  });
  const rendered = query.toString();
  return rendered ? `?${rendered}` : "";
}

export function fetchIncidents(
  filters: { status?: string | undefined; severity?: string | undefined } = {},
) {
  return incidentsApiClient.get<IncidentResponse[]>(
    `/api/v1/incidents${params({ status: filters.status, severity: filters.severity })}`,
  );
}

export function fetchIncident(id: string) {
  return incidentsApiClient.get<IncidentDetailResponse>(`/api/v1/incidents/${id}`);
}

export function resolveIncident(id: string) {
  return incidentsApiClient.post<IncidentDetailResponse>(`/api/v1/incidents/${id}/resolve`, {});
}

export function fetchRunbooks(scenarioQuery?: string) {
  return incidentsApiClient.get<RunbookResponse[]>(
    `/api/v1/runbooks${params({ scenario_query: scenarioQuery })}`,
  );
}

export function fetchRunbook(id: string) {
  return incidentsApiClient.get<RunbookResponse>(`/api/v1/runbooks/${id}`);
}

export function fetchRunbookByScenario(scenario: string) {
  return incidentsApiClient.get<RunbookResponse | null>(
    `/api/v1/runbooks/by-scenario/${encodeURIComponent(scenario)}`,
  );
}

export function createRunbook(payload: RunbookCreateRequest) {
  return incidentsApiClient.post<RunbookResponse>("/api/v1/admin/runbooks", payload);
}

export function updateRunbook(id: string, payload: RunbookUpdateRequest) {
  return incidentsApiClient.patch<RunbookResponse>(`/api/v1/admin/runbooks/${id}`, payload);
}

export function fetchPostMortem(id: string) {
  return incidentsApiClient.get<PostMortemResponse>(`/api/v1/post-mortems/${id}`);
}

export function fetchPostMortemByIncident(incidentId: string) {
  return incidentsApiClient.get<PostMortemResponse>(
    `/api/v1/incidents/${incidentId}/post-mortem`,
  );
}

export function startPostMortem(incidentId: string) {
  return incidentsApiClient.post<PostMortemResponse>(`/api/v1/incidents/${incidentId}/post-mortem`, {});
}

export function updatePostMortemSections(
  id: string,
  payload: { impact_assessment?: string; root_cause?: string; action_items?: unknown[] },
) {
  return incidentsApiClient.patch<PostMortemResponse>(`/api/v1/post-mortems/${id}`, payload);
}

export function markPostMortemBlameless(id: string) {
  return incidentsApiClient.post<PostMortemResponse>(`/api/v1/post-mortems/${id}/blameless`, {});
}

export function distributePostMortem(id: string, recipients: string[]) {
  return incidentsApiClient.post<PostMortemResponse>(`/api/v1/post-mortems/${id}/distribute`, {
    recipients,
  });
}

export function fetchIntegrations() {
  return incidentsApiClient.get<IntegrationResponse[]>("/api/v1/admin/incidents/integrations");
}

export function createIntegration(payload: IntegrationCreateRequest) {
  return incidentsApiClient.post<IntegrationResponse>("/api/v1/admin/incidents/integrations", payload);
}

export function updateIntegration(id: string, payload: IntegrationUpdateRequest) {
  return incidentsApiClient.patch<IntegrationResponse>(
    `/api/v1/admin/incidents/integrations/${id}`,
    payload,
  );
}

export function deleteIntegration(id: string) {
  return incidentsApiClient.delete<void>(`/api/v1/admin/incidents/integrations/${id}`);
}

export function useIncidents(
  filters: { status?: string | undefined; severity?: string | undefined } = {},
) {
  return useAppQuery(incidentQueryKeys.incidents(filters.status, filters.severity), () =>
    fetchIncidents(filters),
  );
}

export function useIncident(id?: string | null) {
  return useAppQuery(incidentQueryKeys.incident(id), () => fetchIncident(id ?? ""), {
    enabled: Boolean(id),
  });
}

export function useRunbooks(scenarioQuery?: string | null) {
  return useAppQuery(incidentQueryKeys.runbooks(scenarioQuery), () =>
    fetchRunbooks(scenarioQuery ?? undefined),
  );
}

export function useRunbook(id?: string | null) {
  return useAppQuery(incidentQueryKeys.runbook(id), () => fetchRunbook(id ?? ""), {
    enabled: Boolean(id),
  });
}

export function useRunbookByScenario(scenario?: string | null) {
  return useAppQuery(
    incidentQueryKeys.runbookScenario(scenario),
    () => fetchRunbookByScenario(scenario ?? ""),
    { enabled: Boolean(scenario) },
  );
}

export function usePostMortem(id?: string | null) {
  return useAppQuery(incidentQueryKeys.postMortem(id), () => fetchPostMortem(id ?? ""), {
    enabled: Boolean(id),
  });
}

export function usePostMortemByIncident(incidentId?: string | null) {
  return useAppQuery(
    incidentQueryKeys.postMortemByIncident(incidentId),
    () => fetchPostMortemByIncident(incidentId ?? ""),
    { enabled: Boolean(incidentId) },
  );
}

export function useIntegrations() {
  return useAppQuery(incidentQueryKeys.integrations(), fetchIntegrations);
}

export function useResolveIncident() {
  return useAppMutation(resolveIncident, { invalidateKeys: [["incidents"]] });
}

export function useStartPostMortem() {
  return useAppMutation(startPostMortem, { invalidateKeys: [["post-mortems"], ["incidents"]] });
}
