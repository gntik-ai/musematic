"use client";

import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";

export type RegionRole = "primary" | "secondary";
export type ReplicationComponent =
  | "postgres"
  | "kafka"
  | "s3"
  | "clickhouse"
  | "qdrant"
  | "neo4j"
  | "opensearch";
export type ReplicationHealth = "healthy" | "degraded" | "unhealthy" | "paused";
export type FailoverPlanRunOutcome = "succeeded" | "failed" | "aborted" | "in_progress";
export type MaintenanceWindowStatus = "scheduled" | "active" | "completed" | "cancelled";
export type CapacityConfidence = "ok" | "low" | "insufficient_history";

export interface RegionConfigResponse {
  id: string;
  region_code: string;
  region_role: RegionRole;
  endpoint_urls: Record<string, unknown>;
  rpo_target_minutes: number;
  rto_target_minutes: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReplicationStatusResponse {
  id?: string | null;
  source_region: string;
  target_region: string;
  component: ReplicationComponent;
  lag_seconds: number | null;
  health: ReplicationHealth;
  pause_reason?: string | null;
  error_detail?: string | null;
  measured_at?: string | null;
  threshold_seconds?: number | null;
  missing_probe: boolean;
}

export interface ReplicationOverviewResponse {
  items: ReplicationStatusResponse[];
  generated_at: string;
}

export interface FailoverPlanStep {
  kind: string;
  name: string;
  parameters: Record<string, unknown>;
}

export interface FailoverPlanResponse {
  id: string;
  name: string;
  from_region: string;
  to_region: string;
  steps: FailoverPlanStep[];
  runbook_url?: string | null;
  tested_at?: string | null;
  last_executed_at?: string | null;
  created_by?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  is_stale: boolean;
}

export interface FailoverPlanRunResponse {
  id: string;
  plan_id: string;
  run_kind: "rehearsal" | "production";
  outcome: FailoverPlanRunOutcome;
  started_at: string;
  ended_at?: string | null;
  step_outcomes: Array<{
    step_index: number;
    kind: string;
    name: string;
    outcome: FailoverPlanRunOutcome;
    duration_ms: number;
    error_detail?: string | null;
  }>;
  initiated_by?: string | null;
  reason?: string | null;
}

export interface MaintenanceWindowResponse {
  id: string;
  starts_at: string;
  ends_at: string;
  reason?: string | null;
  blocks_writes: boolean;
  announcement_text?: string | null;
  status: MaintenanceWindowStatus;
  scheduled_by?: string | null;
  enabled_at?: string | null;
  disabled_at?: string | null;
  disable_failure_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CapacityRecommendation {
  action: string;
  link: string;
  reason: string;
}

export interface CapacitySignalResponse {
  resource_class: string;
  historical_trend: Array<Record<string, unknown>>;
  projection?: Record<string, unknown> | null;
  saturation_horizon?: Record<string, unknown> | null;
  confidence: CapacityConfidence;
  recommendation?: CapacityRecommendation | null;
  generated_at: string;
}

export interface UpgradeStatusResponse {
  runtime_versions: Array<{
    runtime_id: string;
    version: string;
    status: string;
    coexistence_until?: string | null;
  }>;
  documentation_links: Record<string, string>;
}

const REGIONS_API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const regionsApiClient = createApiClient(REGIONS_API_BASE_URL);

export const regionsQueryKeys = {
  regions: ["multi-region", "regions"] as const,
  replicationStatus: ["multi-region", "replication-status"] as const,
  failoverPlans: ["multi-region", "failover-plans"] as const,
  failoverPlanRuns: (planId?: string | null) =>
    ["multi-region", "failover-plan-runs", planId ?? "none"] as const,
  maintenanceWindows: ["multi-region", "maintenance-windows"] as const,
  activeMaintenanceWindow: ["multi-region", "maintenance-window-active"] as const,
  capacityOverview: (workspaceId?: string | null) =>
    ["multi-region", "capacity", workspaceId ?? "platform"] as const,
  upgradeStatus: ["multi-region", "upgrade-status"] as const,
};

export function fetchRegions() {
  return regionsApiClient.get<RegionConfigResponse[]>("/api/v1/regions");
}

export function fetchReplicationStatus() {
  return regionsApiClient.get<ReplicationOverviewResponse>("/api/v1/regions/replication-status");
}

export function fetchFailoverPlans() {
  return regionsApiClient.get<FailoverPlanResponse[]>("/api/v1/regions/failover-plans");
}

export function fetchFailoverPlanRuns(planId: string) {
  return regionsApiClient.get<FailoverPlanRunResponse[]>(
    `/api/v1/regions/failover-plans/${planId}/runs`,
  );
}

export function fetchMaintenanceWindows() {
  return regionsApiClient.get<MaintenanceWindowResponse[]>("/api/v1/maintenance/windows");
}

export function fetchActiveMaintenanceWindow() {
  return regionsApiClient.get<MaintenanceWindowResponse | null>(
    "/api/v1/maintenance/windows/active",
  );
}

export function fetchCapacityOverview(workspaceId?: string | null) {
  const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
  return regionsApiClient.get<CapacitySignalResponse[]>(`/api/v1/regions/capacity${query}`);
}

export function fetchUpgradeStatus() {
  return regionsApiClient.get<UpgradeStatusResponse>("/api/v1/regions/upgrade-status");
}

export function useRegions() {
  return useAppQuery(regionsQueryKeys.regions, fetchRegions);
}

export function useReplicationStatus() {
  return useAppQuery(regionsQueryKeys.replicationStatus, fetchReplicationStatus, {
    refetchInterval: 30_000,
  });
}

export function useFailoverPlans() {
  return useAppQuery(regionsQueryKeys.failoverPlans, fetchFailoverPlans, {
    refetchInterval: 60_000,
  });
}

export function useFailoverPlanRuns(planId?: string | null) {
  return useAppQuery(
    regionsQueryKeys.failoverPlanRuns(planId),
    () => fetchFailoverPlanRuns(planId ?? ""),
    { enabled: Boolean(planId), refetchInterval: 5_000 },
  );
}

export function useMaintenanceWindows() {
  return useAppQuery(regionsQueryKeys.maintenanceWindows, fetchMaintenanceWindows, {
    refetchInterval: 30_000,
  });
}

export function useActiveMaintenanceWindow() {
  return useAppQuery(regionsQueryKeys.activeMaintenanceWindow, fetchActiveMaintenanceWindow, {
    refetchInterval: 15_000,
  });
}

export function useCapacityOverview(workspaceId?: string | null) {
  return useAppQuery(
    regionsQueryKeys.capacityOverview(workspaceId),
    () => fetchCapacityOverview(workspaceId),
    { refetchInterval: 60_000 },
  );
}

export function useUpgradeStatus() {
  return useAppQuery(regionsQueryKeys.upgradeStatus, fetchUpgradeStatus, {
    refetchInterval: 60_000,
  });
}
