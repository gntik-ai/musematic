# Data Model: Fleet Dashboard

**Feature**: 042-fleet-dashboard  
**Type**: Frontend TypeScript types and component state model (no new DB tables — data sourced from fleet management API 033, fleet learning API 033, simulation API 040)

---

## TypeScript Types

### Fleet List Entry

```typescript
// Fleet list item (from GET /api/v1/fleets)
interface FleetListEntry {
  id: string;
  workspace_id: string;
  name: string;
  status: FleetStatus;
  topology_type: FleetTopologyType;
  quorum_min: number;
  member_count: number;
  health_pct: number;             // 0–100, from health projection
  created_at: string;             // ISO8601
  updated_at: string;
}

type FleetStatus = "active" | "degraded" | "paused" | "archived";
type FleetTopologyType = "hierarchical" | "peer_to_peer" | "hybrid";
```

### Fleet Detail

```typescript
// Full fleet record (extends list entry with relationships)
interface FleetDetail extends FleetListEntry {
  members: FleetMember[];
  topology_version: FleetTopologyVersion;
  orchestration_rules: FleetOrchestrationRules | null;
  governance_chain: FleetGovernanceChain | null;
  personality_profile: FleetPersonalityProfile | null;
}
```

### Fleet Member

```typescript
// (from GET /api/v1/fleets/{fleet_id}/members)
interface FleetMember {
  id: string;
  fleet_id: string;
  agent_fqn: string;
  agent_name: string;             // display name from registry
  role: FleetMemberRole;
  availability: FleetMemberAvailability;
  health_pct: number;             // 0–100, individual health
  status: FleetMemberStatus;      // derived from availability + health
  joined_at: string;
  last_error: string | null;      // most recent error message
}

type FleetMemberRole = "lead" | "worker" | "observer";
type FleetMemberAvailability = "available" | "unavailable";
type FleetMemberStatus = "active" | "idle" | "errored";
```

### Fleet Health Projection

```typescript
// (from GET /api/v1/fleets/{fleet_id}/health)
interface FleetHealthProjection {
  fleet_id: string;
  status: FleetStatus;
  health_pct: number;             // 0–100 composite
  quorum_met: boolean;
  available_count: number;
  total_count: number;
  member_statuses: FleetMemberHealthStatus[];
  last_updated: string;
}

interface FleetMemberHealthStatus {
  agent_fqn: string;
  health_pct: number;
  availability: FleetMemberAvailability;
}
```

### Fleet Topology Version

```typescript
// (from fleet detail or topology history)
interface FleetTopologyVersion {
  id: string;
  fleet_id: string;
  topology_type: FleetTopologyType;
  version: number;
  config: TopologyConfig;
  is_current: boolean;
  created_at: string;
}

interface TopologyConfig {
  nodes: TopologyNodeDef[];
  edges: TopologyEdgeDef[];
}

interface TopologyNodeDef {
  id: string;                     // member_id
  agent_fqn: string;
  role: FleetMemberRole;
}

interface TopologyEdgeDef {
  source: string;                 // member_id
  target: string;                 // member_id
  type: "communication" | "delegation" | "observation";
}
```

### Fleet Performance Profile

```typescript
// (from GET /api/v1/fleets/{fleet_id}/performance-profile/history)
interface FleetPerformanceProfile {
  id: string;
  fleet_id: string;
  period_start: string;           // ISO8601
  period_end: string;
  avg_completion_time_ms: number;
  success_rate: number;           // 0.0–1.0
  cost_per_task: number;
  avg_quality_score: number;      // 0.0–1.0
  throughput_per_hour: number;
  member_metrics: Record<string, MemberMetric>;
  flagged_member_fqns: string[];
}

interface MemberMetric {
  success_rate: number;
  avg_completion_time_ms: number;
  task_count: number;
}
```

### Observer Finding

```typescript
// (from GET /api/v1/fleets/{fleet_id}/observer-findings)
interface ObserverFinding {
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

type ObserverFindingSeverity = "info" | "warning" | "critical";
```

### Fleet Orchestration Rules

```typescript
interface FleetOrchestrationRules {
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
```

### Fleet Governance Chain

```typescript
interface FleetGovernanceChain {
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
```

### Fleet Personality Profile

```typescript
interface FleetPersonalityProfile {
  id: string;
  fleet_id: string;
  communication_style: "verbose" | "concise" | "structured";
  decision_speed: "fast" | "deliberate" | "consensus_seeking";
  risk_tolerance: "conservative" | "moderate" | "aggressive";
  autonomy_level: "supervised" | "semi_autonomous" | "fully_autonomous";
  version: number;
  is_current: boolean;
}
```

### Stress Test

```typescript
// Stress test trigger (delegates to simulation API 040)
interface StressTestConfig {
  fleet_id: string;
  duration_minutes: number;
  load_level: "low" | "medium" | "high";
  workspace_id: string;
}

interface StressTestProgress {
  simulation_run_id: string;
  status: "provisioning" | "running" | "completed" | "cancelled" | "failed";
  elapsed_seconds: number;
  total_seconds: number;
  simulated_executions: number;
  current_success_rate: number;
  current_avg_latency_ms: number;
}
```

---

## Component State Model

### Topology Viewport State (Zustand — optional)

```typescript
// Persists zoom/pan across tab switches within the same fleet detail session
interface TopologyViewportState {
  viewport: { x: number; y: number; zoom: number } | null;
  selectedNodeId: string | null;
  expandedGroups: string[];       // group node IDs that are expanded
  // Actions
  setViewport: (vp: { x: number; y: number; zoom: number }) => void;
  selectNode: (nodeId: string | null) => void;
  toggleGroup: (groupId: string) => void;
  reset: () => void;
}
```

---

## Fleet List Filter State

```typescript
// URL search params managed via useSearchParams()
interface FleetListFilters {
  search: string;                 // free-text filter (debounced 300ms)
  topology_type: FleetTopologyType[];
  status: FleetStatus[];
  health_min: number | null;      // minimum health score threshold
  sort_by: "name" | "health_pct" | "member_count" | "updated_at";
  sort_order: "asc" | "desc";
  page: number;
  size: number;                   // default 20
}
```

---

## Performance Chart Time Range

```typescript
type PerformanceTimeRange = "1h" | "6h" | "24h" | "7d" | "30d";

// Maps to query parameters on the history endpoint
const TIME_RANGE_MAP: Record<PerformanceTimeRange, { hours: number }> = {
  "1h": { hours: 1 },
  "6h": { hours: 6 },
  "24h": { hours: 24 },
  "7d": { hours: 168 },
  "30d": { hours: 720 },
};
```
