export type FleetStatus = "active" | "degraded" | "paused" | "archived";
export type FleetTopologyType = "hierarchical" | "peer_to_peer" | "hybrid";
export type FleetMemberRole = "lead" | "worker" | "observer";
export type FleetMemberAvailability = "available" | "unavailable";
export type FleetMemberStatus = "active" | "idle" | "errored";
export type ObserverFindingSeverity = "info" | "warning" | "critical";
export type PerformanceTimeRange = "1h" | "6h" | "24h" | "7d" | "30d";
export type FleetDetailTab =
  | "topology"
  | "members"
  | "performance"
  | "controls"
  | "observers";

export interface FleetListEntry {
  id: string;
  workspace_id: string;
  name: string;
  status: FleetStatus;
  topology_type: FleetTopologyType;
  quorum_min: number;
  member_count: number;
  health_pct: number;
  created_at: string;
  updated_at: string;
}

export interface FleetDetail extends FleetListEntry {
  members: FleetMember[];
  topology_version: FleetTopologyVersion | null;
  orchestration_rules: FleetOrchestrationRules | null;
  governance_chain: FleetGovernanceChain | null;
  personality_profile: FleetPersonalityProfile | null;
}

export interface FleetMember {
  id: string;
  fleet_id: string;
  agent_fqn: string;
  agent_name: string;
  role: FleetMemberRole;
  availability: FleetMemberAvailability;
  health_pct: number;
  status: FleetMemberStatus;
  joined_at: string;
  last_error: string | null;
}

export interface FleetMemberHealthStatus {
  agent_fqn: string;
  health_pct: number;
  availability: FleetMemberAvailability;
}

export interface FleetHealthProjection {
  fleet_id: string;
  status: FleetStatus;
  health_pct: number;
  quorum_met: boolean;
  available_count: number;
  total_count: number;
  member_statuses: FleetMemberHealthStatus[];
  last_updated: string;
}

export interface TopologyNodeDef {
  id: string;
  agent_fqn: string;
  role: FleetMemberRole;
}

export interface TopologyEdgeDef {
  source: string;
  target: string;
  type: "communication" | "delegation" | "observation";
}

export interface TopologyConfig {
  nodes: TopologyNodeDef[];
  edges: TopologyEdgeDef[];
}

export interface FleetTopologyVersion {
  id: string;
  fleet_id: string;
  topology_type: FleetTopologyType;
  version: number;
  config: TopologyConfig;
  is_current: boolean;
  created_at: string;
}

export interface MemberMetric {
  success_rate: number;
  avg_completion_time_ms: number;
  task_count: number;
}

export interface FleetPerformanceProfile {
  id: string;
  fleet_id: string;
  period_start: string;
  period_end: string;
  avg_completion_time_ms: number;
  success_rate: number;
  cost_per_task: number;
  avg_quality_score: number;
  throughput_per_hour: number;
  member_metrics: Record<string, MemberMetric>;
  flagged_member_fqns: string[];
}

export interface ObserverFinding {
  id: string;
  fleet_id: string;
  observer_fqn: string;
  observer_name: string;
  severity: ObserverFindingSeverity;
  description: string;
  suggested_actions: string[];
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  created_at: string;
}

export interface FleetOrchestrationRules {
  id: string;
  fleet_id: string;
  version: number;
  delegation: Record<string, unknown>;
  aggregation: Record<string, unknown>;
  escalation: Record<string, unknown>;
  conflict_resolution: Record<string, unknown>;
  retry: Record<string, unknown>;
  max_parallelism: number;
  is_current: boolean;
}

export interface FleetGovernanceChain {
  id: string;
  fleet_id: string;
  version: number;
  observer_fqns: string[];
  judge_fqns: string[];
  enforcer_fqns: string[];
  policy_binding_ids: string[];
  is_current: boolean;
  is_default: boolean;
}

export interface FleetPersonalityProfile {
  id: string;
  fleet_id: string;
  communication_style: "verbose" | "concise" | "structured";
  decision_speed: "fast" | "deliberate" | "consensus_seeking";
  risk_tolerance: "conservative" | "moderate" | "aggressive";
  autonomy_level: "supervised" | "semi_autonomous" | "fully_autonomous";
  version: number;
  is_current: boolean;
}

export interface StressTestConfig {
  fleet_id: string;
  duration_minutes: number;
  load_level: "low" | "medium" | "high";
  workspace_id: string;
}

export interface StressTestProgress {
  simulation_run_id: string;
  status: "provisioning" | "running" | "completed" | "cancelled" | "failed";
  elapsed_seconds: number;
  total_seconds: number;
  simulated_executions: number;
  current_success_rate: number;
  current_avg_latency_ms: number;
}

export interface FleetListFilters {
  search: string;
  topology_type: FleetTopologyType[];
  status: FleetStatus[];
  tags: string[];
  labels: Record<string, string>;
  health_min: number | null;
  sort_by: "name" | "health_pct" | "member_count" | "updated_at";
  sort_order: "asc" | "desc";
  page: number;
  size: number;
}

export interface ObserverFindingFilters {
  severity: ObserverFindingSeverity | null;
  acknowledged: boolean | null;
  cursor?: string | null;
  limit?: number;
}

export interface FleetActionResponse {
  status: string;
  active_executions?: number;
}

export interface AcknowledgeFindingInput {
  fleetId: string;
  findingId: string;
}

export interface AddFleetMemberInput {
  fleetId: string;
  agentFqn: string;
  role: FleetMemberRole;
}

export interface RemoveFleetMemberInput {
  fleetId: string;
  memberId: string;
}

export interface UpdateFleetMemberRoleInput extends RemoveFleetMemberInput {
  role: FleetMemberRole;
}

export interface FleetScalePreviewEntry {
  agent_fqn: string;
  agent_name: string;
  role: FleetMemberRole;
}

export const DEFAULT_FLEET_LIST_FILTERS: FleetListFilters = {
  search: "",
  topology_type: [],
  status: [],
  tags: [],
  labels: {},
  health_min: null,
  sort_by: "updated_at",
  sort_order: "desc",
  page: 1,
  size: 20,
};

export const FLEET_DETAIL_TABS: FleetDetailTab[] = [
  "topology",
  "members",
  "performance",
  "controls",
  "observers",
];

export const FLEET_STATUS_LABELS: Record<FleetStatus, string> = {
  active: "Active",
  degraded: "Degraded",
  paused: "Paused",
  archived: "Archived",
};

export const FLEET_TOPOLOGY_LABELS: Record<FleetTopologyType, string> = {
  hierarchical: "Hierarchical",
  peer_to_peer: "Mesh",
  hybrid: "Hybrid",
};

export const PERFORMANCE_TIME_RANGE_LABELS: Record<PerformanceTimeRange, string> = {
  "1h": "1h",
  "6h": "6h",
  "24h": "24h",
  "7d": "7d",
  "30d": "30d",
};

export const TIME_RANGE_MAP: Record<PerformanceTimeRange, { hours: number }> = {
  "1h": { hours: 1 },
  "6h": { hours: 6 },
  "24h": { hours: 24 },
  "7d": { hours: 24 * 7 },
  "30d": { hours: 24 * 30 },
};

export function isFleetDetailTab(value: string | null | undefined): value is FleetDetailTab {
  return FLEET_DETAIL_TABS.includes((value ?? "") as FleetDetailTab);
}

export function getFleetHealthTone(healthPct: number): "critical" | "warning" | "healthy" {
  if (healthPct < 40) {
    return "critical";
  }
  if (healthPct < 70) {
    return "warning";
  }
  return "healthy";
}
