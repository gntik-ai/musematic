import type {
  FleetDetail,
  FleetGovernanceChain,
  FleetHealthProjection,
  FleetListEntry,
  FleetMember,
  FleetOrchestrationRules,
  FleetPerformanceProfile,
  FleetPersonalityProfile,
  FleetTopologyVersion,
  ObserverFinding,
} from "@/lib/types/fleet";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export const sampleMembers: FleetMember[] = [
  {
    id: "member-1",
    fleet_id: "fleet-1",
    agent_fqn: "risk:triage-lead",
    agent_name: "Triage Lead",
    role: "lead",
    availability: "available",
    health_pct: 92,
    status: "active",
    joined_at: "2026-04-15T08:00:00.000Z",
    last_error: null,
  },
  {
    id: "member-2",
    fleet_id: "fleet-1",
    agent_fqn: "risk:worker-one",
    agent_name: "Worker One",
    role: "worker",
    availability: "available",
    health_pct: 68,
    status: "idle",
    joined_at: "2026-04-15T08:05:00.000Z",
    last_error: null,
  },
  {
    id: "member-3",
    fleet_id: "fleet-1",
    agent_fqn: "risk:observer-one",
    agent_name: "Observer One",
    role: "observer",
    availability: "unavailable",
    health_pct: 31,
    status: "errored",
    joined_at: "2026-04-15T08:10:00.000Z",
    last_error: "Escalation pipeline timeout",
  },
];

export const sampleFleetListEntries: FleetListEntry[] = [
  {
    id: "fleet-1",
    workspace_id: "workspace-1",
    name: "Fraud mesh",
    status: "degraded",
    topology_type: "hybrid",
    quorum_min: 2,
    member_count: 3,
    health_pct: 62,
    created_at: "2026-04-15T07:00:00.000Z",
    updated_at: "2026-04-16T11:00:00.000Z",
  },
  {
    id: "fleet-2",
    workspace_id: "workspace-1",
    name: "KYC review",
    status: "active",
    topology_type: "hierarchical",
    quorum_min: 1,
    member_count: 4,
    health_pct: 91,
    created_at: "2026-04-15T07:00:00.000Z",
    updated_at: "2026-04-16T12:00:00.000Z",
  },
];

const primaryFleet = sampleFleetListEntries[0]!;

export const sampleTopologyVersion: FleetTopologyVersion = {
  id: "topology-1",
  fleet_id: "fleet-1",
  topology_type: "hybrid",
  version: 3,
  is_current: true,
  created_at: "2026-04-16T10:00:00.000Z",
  config: {
    nodes: sampleMembers.map((member) => ({
      id: member.id,
      agent_fqn: member.agent_fqn,
      role: member.role,
    })),
    edges: [
      { source: "member-1", target: "member-2", type: "delegation" },
      { source: "member-2", target: "member-3", type: "observation" },
    ],
  },
};

export const sampleHealthProjection: FleetHealthProjection = {
  fleet_id: "fleet-1",
  status: "degraded",
  health_pct: 62,
  quorum_met: true,
  available_count: 2,
  total_count: 3,
  last_updated: "2026-04-16T11:00:00.000Z",
  member_statuses: sampleMembers.map((member) => ({
    agent_fqn: member.agent_fqn,
    health_pct: member.health_pct,
    availability: member.availability,
  })),
};

export const samplePerformanceHistory: FleetPerformanceProfile[] = [
  {
    id: "perf-1",
    fleet_id: "fleet-1",
    period_start: "2026-04-16T09:00:00.000Z",
    period_end: "2026-04-16T10:00:00.000Z",
    avg_completion_time_ms: 1200,
    success_rate: 0.95,
    cost_per_task: 0.38,
    avg_quality_score: 0.82,
    throughput_per_hour: 24,
    member_metrics: {},
    flagged_member_fqns: [],
  },
  {
    id: "perf-2",
    fleet_id: "fleet-1",
    period_start: "2026-04-16T10:00:00.000Z",
    period_end: "2026-04-16T11:00:00.000Z",
    avg_completion_time_ms: 1420,
    success_rate: 0.91,
    cost_per_task: 0.41,
    avg_quality_score: 0.79,
    throughput_per_hour: 21,
    member_metrics: {},
    flagged_member_fqns: [],
  },
];

export const sampleFindings: ObserverFinding[] = [
  {
    id: "finding-1",
    fleet_id: "fleet-1",
    observer_fqn: "risk:observer-one",
    observer_name: "Observer One",
    severity: "critical",
    description: "Latency spike detected in fraud escalation workflow.",
    suggested_actions: ["Reduce max parallelism", "Inspect downstream connector"],
    acknowledged: false,
    acknowledged_by: null,
    acknowledged_at: null,
    created_at: "2026-04-16T11:10:00.000Z",
  },
  {
    id: "finding-2",
    fleet_id: "fleet-1",
    observer_fqn: "risk:observer-one",
    observer_name: "Observer One",
    severity: "info",
    description: "Observer confidence baseline recalculated.",
    suggested_actions: ["No action required"],
    acknowledged: true,
    acknowledged_by: "user-1",
    acknowledged_at: "2026-04-16T11:15:00.000Z",
    created_at: "2026-04-16T11:14:00.000Z",
  },
];

export const sampleFleetDetail: FleetDetail = {
  id: primaryFleet.id,
  workspace_id: primaryFleet.workspace_id,
  name: primaryFleet.name,
  status: primaryFleet.status,
  topology_type: primaryFleet.topology_type,
  quorum_min: primaryFleet.quorum_min,
  member_count: primaryFleet.member_count,
  health_pct: primaryFleet.health_pct,
  created_at: primaryFleet.created_at,
  updated_at: primaryFleet.updated_at,
  members: sampleMembers,
  topology_version: sampleTopologyVersion,
  orchestration_rules: {
    id: "orch-1",
    fleet_id: "fleet-1",
    version: 2,
    delegation: {},
    aggregation: {},
    escalation: {},
    conflict_resolution: {},
    retry: {},
    max_parallelism: 5,
    is_current: true,
  },
  governance_chain: {
    id: "gov-1",
    fleet_id: "fleet-1",
    version: 1,
    observer_fqns: ["risk:observer-one"],
    judge_fqns: ["risk:judge-one"],
    enforcer_fqns: ["risk:enforcer-one"],
    policy_binding_ids: ["policy-1"],
    is_current: true,
    is_default: true,
  },
  personality_profile: {
    id: "persona-1",
    fleet_id: "fleet-1",
    communication_style: "structured",
    decision_speed: "deliberate",
    risk_tolerance: "moderate",
    autonomy_level: "semi_autonomous",
    version: 1,
    is_current: true,
  },
};

export const sampleGovernanceChain: FleetGovernanceChain =
  sampleFleetDetail.governance_chain!;
export const sampleOrchestrationRules: FleetOrchestrationRules =
  sampleFleetDetail.orchestration_rules!;
export const samplePersonalityProfile: FleetPersonalityProfile =
  sampleFleetDetail.personality_profile!;

export function seedFleetStores() {
  useAuthStore.setState({
    accessToken: "access-token",
    isAuthenticated: true,
    refreshToken: "refresh-token",
    user: {
      id: "user-1",
      email: "operator@musematic.dev",
      displayName: "Operator",
      avatarUrl: null,
      mfaEnrolled: true,
      roles: ["agent_operator", "workspace_admin"],
      workspaceId: "workspace-1",
    },
  } as never);

  useWorkspaceStore.setState({
    currentWorkspace: {
      id: "workspace-1",
      name: "Risk Ops",
      slug: "risk-ops",
      description: "Risk operations workspace",
      memberCount: 8,
      createdAt: "2026-04-10T09:00:00.000Z",
    },
    isLoading: false,
    sidebarCollapsed: false,
    workspaceList: [],
  } as never);
}
