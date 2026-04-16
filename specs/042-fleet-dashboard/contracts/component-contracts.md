# Component Contracts: Fleet Dashboard

Documents key component prop interfaces and rendering contracts.

---

## FleetDataTable

```typescript
interface FleetDataTableProps {
  workspace_id: string;
}
// Internal: uses useFleets() with useSearchParams() for filter state
// Columns: name, topology type badge, member count, health score (inline gauge), status badge
// Renders: shadcn DataTable + SearchInput + FilterBar + pagination
// Navigation: onClick row → router.push(`/fleet/${fleet_id}`)
```

---

## FleetStatusBadge

```typescript
interface FleetStatusBadgeProps {
  status: FleetStatus;
}
// Colors: active=green, degraded=yellow, paused=blue, archived=gray
// Uses shadcn Badge with variant mapping
```

---

## FleetTopologyBadge

```typescript
interface FleetTopologyBadgeProps {
  topology: FleetTopologyType;
}
// Labels: hierarchical="Hierarchical", peer_to_peer="Mesh", hybrid="Hybrid"
// Uses shadcn Badge (outline variant)
```

---

## FleetDetailView

```typescript
interface FleetDetailViewProps {
  fleetId: string;
}
// Internal: uses useFleet(fleetId) to load fleet detail
// shadcn Tabs with URL query param routing:
//   ?tab=topology|members|performance|controls|observers
// Default tab: topology
// Header: fleet name, status badge, topology badge, health gauge (sm)
```

---

## FleetTopologyGraph

```typescript
interface FleetTopologyGraphProps {
  fleetId: string;
  onNodeSelect?: (memberId: string | null) => void;
}
// Internal: uses useFleetTopology(fleetId), useFleetMembers(fleetId), useFleetHealth(fleetId)
// Renders: @xyflow/react ReactFlow with dagre layout
// Custom nodes: FleetMemberNode
// Custom edges: CommunicationEdge
// Features: zoom, pan, minimap, background grid
// Clustering: group nodes by role when count > 50
// WebSocket: subscribes to fleet:{fleetId} for real-time health color updates
```

---

## FleetMemberNode

```typescript
interface FleetMemberNodeData {
  agent_fqn: string;
  agent_name: string;
  role: FleetMemberRole;
  health_pct: number;
  availability: FleetMemberAvailability;
  status: FleetMemberStatus;
}
// Custom @xyflow/react node component
// Renders: agent name, role badge, health-colored border (green/yellow/red)
// Size: "sm" for normal, "lg" for selected
// Click: triggers onNodeSelect
```

---

## CommunicationEdge

```typescript
interface CommunicationEdgeData {
  type: "communication" | "delegation" | "observation";
}
// Custom @xyflow/react edge component
// communication: solid line, animated dashes when active
// delegation: dashed line with arrow
// observation: dotted line (lighter color)
```

---

## FleetMemberDetailPanel

```typescript
interface FleetMemberDetailPanelProps {
  fleetId: string;
  memberId: string;
  onClose: () => void;
}
// Slide-in side panel (shadcn Sheet) showing selected member details
// Shows: name, FQN, role, health gauge (sm), availability, joined date, last error
// Actions: "Remove" button → confirmation, "Change Role" → dropdown
```

---

## FleetMemberPanel

```typescript
interface FleetMemberPanelProps {
  fleetId: string;
}
// Internal: uses useFleetMembers(fleetId)
// Renders: list of members with name, FQN, role badge, health indicator, status
// Actions: "Add Member" button → AddMemberDialog, "Remove" per member → AlertDialog
// Errored members: highlighted with error indicator + tooltip with last_error
```

---

## AddMemberDialog

```typescript
interface AddMemberDialogProps {
  fleetId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onMemberAdded: () => void;
}
// shadcn Dialog with SearchInput for agent discovery
// Uses useAgents() from feature 041 hooks (registry search)
// Role selector: shadcn Select (lead/worker/observer)
// Add button → useAddFleetMember()
```

---

## FleetHealthGauge

```typescript
interface FleetHealthGaugeProps {
  fleetId: string;
  size?: "sm" | "lg";            // sm for header, lg for dedicated section
  showBreakdown?: boolean;       // default true
}
// Internal: uses useFleetHealth(fleetId)
// Extends ScoreGauge with breakdown Tooltip:
//   - quorum_met indicator
//   - available_count / total_count
//   - per-member health via member_statuses[]
// Colors: < 40 = red, 40–70 = yellow, > 70 = green
```

---

## FleetPerformanceCharts

```typescript
interface FleetPerformanceChartsProps {
  fleetId: string;
}
// Internal: uses useFleetPerformanceHistory(fleetId, selectedRange)
// Three Recharts LineChart components with syncId for synchronized tooltips:
//   1. Success Rate (%) — 0–100 y-axis
//   2. Avg Latency (ms) — auto-scaled y-axis
//   3. Cost per Task ($) — auto-scaled y-axis
// Time range selector: shadcn ToggleGroup (1h, 6h, 24h, 7d, 30d)
// Default range: 24h
// Real-time: WebSocket updates append new data points
```

---

## FleetControlsPanel

```typescript
interface FleetControlsPanelProps {
  fleetId: string;
  currentStatus: FleetStatus;
}
// Pause button: visible when active/degraded → usePauseFleet → AlertDialog
// Resume button: visible when paused → useResumeFleet → AlertDialog
// Scale button: opens ScaleDialog
// Stress Test button: opens StressTestDialog (disabled if test already running)
// All buttons show real-time status transitions during execution
```

---

## ScaleDialog

```typescript
interface ScaleDialogProps {
  fleetId: string;
  currentMemberCount: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
// shadcn Dialog with number input for target member count
// Preview: shows which agents will be added (from registry search)
// Confirm → sequential useAddFleetMember() calls with progress indicator
```

---

## StressTestDialog

```typescript
interface StressTestDialogProps {
  fleetId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}
// shadcn Dialog with:
//   - Duration: shadcn Select (5min, 15min, 30min, 1h)
//   - Load level: shadcn Select (low, medium, high)
// Confirm → useTriggerStressTest()
// Progress view: replaces form with live progress (useStressTestProgress with 3s refetch)
// Shows: elapsed/total, simulated executions, success rate, latency
// Cancel button → useCancelStressTest()
```

---

## FleetObserverPanel

```typescript
interface FleetObserverPanelProps {
  fleetId: string;
}
// Internal: uses useObserverFindings(fleetId, filters)
// Filter bar: severity selector (info/warning/critical), acknowledged toggle
// Finding list: severity icon + color, timestamp (date-fns), observer name,
//   description, suggested actions (expandable), acknowledge button
// Acknowledge → useAcknowledgeFinding() → optimistic update
```
