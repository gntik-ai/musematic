# API Contracts Consumed: Fleet Dashboard

Documents the backend API endpoints this frontend feature consumes.  
All requests require `Authorization: Bearer <access_token>`.  
Base URL prefix: `/api/v1`

---

## Fleet Management API (feature 033)

### Fleet List
```
GET /api/v1/fleets
  ?workspace_id={id}&status={status}&page={n}&size={n}
→ { items: FleetListEntry[], total: number, page: number, size: number }
```

### Fleet Detail
```
GET /api/v1/fleets/{fleet_id}
→ FleetDetail
Errors: 404 if fleet not found
```

### Fleet Health (Real-time projection from Redis)
```
GET /api/v1/fleets/{fleet_id}/health
→ FleetHealthProjection
```

### Fleet Members
```
GET /api/v1/fleets/{fleet_id}/members
→ { items: FleetMember[] }
```

### Add Fleet Member
```
POST /api/v1/fleets/{fleet_id}/members
body: { agent_fqn: string, role: FleetMemberRole }
→ FleetMember (201)
Errors: 409 if agent already in fleet, 404 if agent not found
```

### Remove Fleet Member
```
DELETE /api/v1/fleets/{fleet_id}/members/{member_id}
→ 204
Errors: 409 if member has active executions (returns execution count)
```

### Update Fleet Member Role
```
PUT /api/v1/fleets/{fleet_id}/members/{member_id}/role
body: { role: FleetMemberRole }
→ FleetMember
```

### Fleet Topology History
```
GET /api/v1/fleets/{fleet_id}/topology/history
→ { items: FleetTopologyVersion[] }
```

### Update Fleet Topology
```
PUT /api/v1/fleets/{fleet_id}/topology
body: { topology_type: FleetTopologyType, config: TopologyConfig }
→ FleetTopologyVersion (creates new version)
```

---

## Fleet Actions API (feature 033)

### Pause Fleet
```
POST /api/v1/fleets/{fleet_id}/pause
→ { status: "pausing", active_executions: number }
```

### Resume Fleet
```
POST /api/v1/fleets/{fleet_id}/resume
→ { status: "active" }
Errors: 409 if fleet not in paused state
```

### Archive Fleet
```
POST /api/v1/fleets/{fleet_id}/archive
→ { status: "archived" }
Note: Irreversible
```

---

## Fleet Learning API (feature 033)

### Performance Profile History (time-series for charts)
```
GET /api/v1/fleets/{fleet_id}/performance-profile/history
  ?period_start={iso8601}&period_end={iso8601}&limit={n}
→ { items: FleetPerformanceProfile[] }
```

### Latest Performance Profile
```
GET /api/v1/fleets/{fleet_id}/performance-profile
→ FleetPerformanceProfile
```

### Trigger Performance Computation
```
POST /api/v1/fleets/{fleet_id}/performance-profile/compute
→ 202 Accepted
```

---

## Fleet Governance API (feature 033)

### Governance Chain
```
GET /api/v1/fleets/{fleet_id}/governance-chain
→ FleetGovernanceChain
```

### Orchestration Rules
```
GET /api/v1/fleets/{fleet_id}/orchestration-rules
→ FleetOrchestrationRules
```

### Personality Profile
```
GET /api/v1/fleets/{fleet_id}/personality-profile
→ FleetPersonalityProfile
```

---

## Observer Findings API (feature 033 / 024)

### List Observer Findings
```
GET /api/v1/fleets/{fleet_id}/observer-findings
  ?severity={info|warning|critical}&acknowledged={true|false}&limit={n}&cursor={cursor}
→ { items: ObserverFinding[], next_cursor: string | null }
```

### Acknowledge Finding
```
POST /api/v1/fleets/{fleet_id}/observer-findings/{finding_id}/acknowledge
→ ObserverFinding
```

---

## Simulation API (feature 040)

### Trigger Stress Test
```
POST /api/v1/simulation/runs
body: { fleet_id: string, workspace_id: string, duration_minutes: number, load_level: string, type: "stress_test" }
→ { simulation_run_id: string, status: "provisioning" } (201)
```

### Get Stress Test Progress
```
GET /api/v1/simulation/runs/{simulation_run_id}
→ StressTestProgress
```

### Cancel Stress Test
```
POST /api/v1/simulation/runs/{simulation_run_id}/cancel
→ { status: "cancelled" }
```

---

## Agent Registry API (feature 021 — for member selection)

### Search Available Agents (for "Add Member" selector)
```
GET /api/v1/registry/agents
  ?workspace_id={id}&status=active&search={term}&limit={n}
→ { items: AgentCatalogEntry[], next_cursor: string | null }
```

---

## TanStack Query Hook Map

| Hook | Endpoint | Type |
|------|----------|------|
| `useFleets(filters)` | GET /fleets | `useQuery` (paginated) |
| `useFleet(fleetId)` | GET /fleets/{fleet_id} | `useQuery` |
| `useFleetHealth(fleetId)` | GET /fleets/{fleet_id}/health | `useQuery` (refetchInterval: 30s fallback) |
| `useFleetMembers(fleetId)` | GET /fleets/{fleet_id}/members | `useQuery` |
| `useFleetPerformanceHistory(fleetId, range)` | GET /fleets/{fleet_id}/performance-profile/history | `useQuery` |
| `useFleetTopology(fleetId)` | GET /fleets/{fleet_id}/topology/history | `useQuery` (latest) |
| `useFleetGovernance(fleetId)` | GET /fleets/{fleet_id}/governance-chain | `useQuery` |
| `useFleetOrchestration(fleetId)` | GET /fleets/{fleet_id}/orchestration-rules | `useQuery` |
| `useFleetPersonality(fleetId)` | GET /fleets/{fleet_id}/personality-profile | `useQuery` |
| `useObserverFindings(fleetId, filters)` | GET /fleets/{fleet_id}/observer-findings | `useQuery` |
| `useAddFleetMember()` | POST /fleets/{fleet_id}/members | `useMutation` |
| `useRemoveFleetMember()` | DELETE /fleets/{fleet_id}/members/{id} | `useMutation` |
| `useUpdateMemberRole()` | PUT /fleets/{fleet_id}/members/{id}/role | `useMutation` |
| `usePauseFleet()` | POST /fleets/{fleet_id}/pause | `useMutation` |
| `useResumeFleet()` | POST /fleets/{fleet_id}/resume | `useMutation` |
| `useAcknowledgeFinding()` | POST /fleets/{fleet_id}/observer-findings/{id}/acknowledge | `useMutation` |
| `useTriggerStressTest()` | POST /simulation/runs | `useMutation` |
| `useStressTestProgress(runId)` | GET /simulation/runs/{id} | `useQuery` (refetchInterval: 3s) |
| `useCancelStressTest()` | POST /simulation/runs/{id}/cancel | `useMutation` |
