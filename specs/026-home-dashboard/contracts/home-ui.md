# UI Contracts: Home Dashboard

**Branch**: `026-home-dashboard` | **Date**: 2026-04-11 | **Phase**: 1

## Overview

This document specifies the API endpoints consumed by the home dashboard, the WebSocket events handled, and the component-level interaction contracts. This is a frontend feature — no new backend endpoints are defined here (backend APIs are pre-existing from bounded contexts 018, 020, 024, execution BC).

---

## API Endpoints Consumed

### GET /api/v1/workspaces/{workspace_id}/analytics/summary

**Source**: Analytics bounded context (feature 020)  
**Used by**: `useWorkspaceSummary` hook  
**Auth**: Bearer JWT (existing middleware)

**Response**:
```typescript
{
  workspace_id: string;
  active_agents: number;
  active_agents_change: number;         // delta from prior period (+ = increased)
  running_executions: number;
  running_executions_change: number;
  pending_approvals: number;
  pending_approvals_change: number;
  cost_current: number;                 // USD cents (e.g., 14250 = $142.50)
  cost_previous: number;
  period_label: string;                 // e.g., "Apr 2026"
}
```

**Dashboard behavior**: Maps to 4 MetricCard components. If this endpoint returns 4xx/5xx, the WorkspaceSummary section shows `SectionError` with retry.

---

### GET /api/v1/workspaces/{workspace_id}/dashboard/recent-activity

**Source**: BFF aggregation endpoint (merges interactions + executions) — new endpoint to be added to the control plane `api` profile  
**Used by**: `useRecentActivity` hook

> **Note**: This is a new BFF-style endpoint the backend needs to expose. It merges the top 10 most recent items from interactions and executions, pre-sorted by `created_at` descending. The frontend calls one endpoint; the backend aggregates.

**Response**:
```typescript
{
  workspace_id: string;
  items: Array<{
    id: string;
    type: "interaction" | "execution";
    title: string;
    status: "running" | "completed" | "failed" | "canceled" | "waiting";
    timestamp: string;                  // ISO 8601
    href: string;                       // /interactions/{id} or /executions/{id}
    metadata: {
      agent_fqn?: string;
      workflow_name?: string;
    };
  }>;
}
```

**Dashboard behavior**: Renders as Timeline component. Empty array → `EmptyState` component. Error → `SectionError` with retry.

---

### GET /api/v1/workspaces/{workspace_id}/dashboard/pending-actions

**Source**: BFF aggregation endpoint (merges approvals + failed executions + attention requests)  
**Used by**: `usePendingActions` hook

> **Note**: This is a new BFF-style endpoint. Merges pending approvals (execution BC), failed executions (execution BC), and open attention requests (interactions BC, feature 024), sorted by urgency: failed executions (high) → attention requests (high/medium) → pending approvals (medium).

**Response**:
```typescript
{
  workspace_id: string;
  total: number;
  items: Array<{
    id: string;
    type: "approval" | "failed_execution" | "attention_request";
    title: string;
    description: string;
    urgency: "high" | "medium" | "low";
    created_at: string;
    href: string;
    actions: Array<{
      id: string;
      label: string;
      variant: "default" | "destructive" | "ghost";
      action: "approve" | "reject" | "navigate";
      endpoint?: string;                // e.g., "/api/v1/workspaces/{ws_id}/approvals/{approval_id}/approve"
      method?: "POST" | "DELETE";
    }>;
  }>;
}
```

**Dashboard behavior**: Renders as Card list. Empty array → `EmptyState` ("All clear — no pending actions"). Error → `SectionError`.

---

### POST /api/v1/workspaces/{workspace_id}/approvals/{approval_id}/approve
### POST /api/v1/workspaces/{workspace_id}/approvals/{approval_id}/reject

**Source**: Execution bounded context (approvals)  
**Used by**: `useApproveMutation` hook (triggered from `PendingActionCard`)

**Response 200**: `{ approved: true }` / `{ rejected: true }`  
**Response 409**: Action already resolved (show toast: "This action has already been resolved")  
**Response 403**: Insufficient permission (show toast: "You don't have permission to perform this action")

---

## WebSocket Events Handled

The dashboard subscribes to three channels via the existing `lib/ws.ts` WebSocketClient.

### channel: `execution`

| Event Type | Action |
|------------|--------|
| `execution.started` | Invalidate `activity` + `summary` queries |
| `execution.completed` | Invalidate `activity` + `summary` queries |
| `execution.failed` | Invalidate `activity` + `summary` + `pending-actions` queries |
| `execution.requires_approval` | Invalidate `pending-actions` + `summary` queries |

### channel: `interaction`

| Event Type | Action |
|------------|--------|
| `interaction.started` | Invalidate `activity` query |
| `interaction.completed` | Invalidate `activity` + `summary` queries |

### channel: `workspace`

| Event Type | Action |
|------------|--------|
| `workspace.approval.created` | Invalidate `pending-actions` + `summary` queries |
| `workspace.approval.resolved` | Invalidate `pending-actions` + `summary` queries |
| `interaction.attention.requested` | Invalidate `pending-actions` query |

### Connection Status Events

| Event | Dashboard Behavior |
|-------|--------------------|
| Connection lost | `ConnectionStatusBanner` appears; all queries switch to `refetchInterval: 30_000` |
| Connection restored | `ConnectionStatusBanner` disappears; all queries refetch immediately; `refetchInterval: false` |

---

## Component Interaction Contracts

### WorkspaceSummary

```
Props: { workspaceId: string }
Loading: 4 skeleton MetricCard components (animate-pulse)
Success: 4 MetricCard components with live data
Error: SectionError with "Retry" button
Empty (all zeros): MetricCard components showing "0" — not an empty state
```

### RecentActivity

```
Props: { workspaceId: string }
Loading: Timeline skeleton (5 placeholder rows, animate-pulse)
Success: Timeline component with ActivityEntry items
Empty: EmptyState — "No recent activity"
Error: SectionError with "Retry" button
WebSocket update: New item prepended to list; list truncated to 10 items
```

### PendingActions

```
Props: { workspaceId: string }
Loading: 3 skeleton Card components (animate-pulse)
Success: PendingActionCard list
Empty: EmptyState — "All clear — no pending actions" (positive framing, green icon)
Error: SectionError with "Retry" button
Action: approve/reject triggers optimistic removal, then query invalidation
```

### QuickActions

```
Props: {} (reads workspace context from store)
State: Static — no loading/error state
Render: 4 shadcn/ui Button components in flex row
Permission check: Disabled buttons show Tooltip with "Requires write access"
Keyboard: All buttons are Tab-focusable with visible focus ring
```

### ConnectionStatusBanner

```
Props: { isConnected: boolean }
Visible when: isConnected === false
Content: "Live updates paused — reconnecting…" with a spinner icon
Animation: Tailwind transition-all for smooth appear/disappear
Position: Below page header, above dashboard content
```

### PendingActionCard

```
Props: { action: PendingAction, workspaceId: string }
Urgency styling:
  high → red left border + StatusBadge "Critical"
  medium → amber left border + StatusBadge "Warning"
  low → no special border + StatusBadge "Info"
Actions:
  "approve" → useMutation → optimistic removal on success
  "reject" → useMutation (destructive variant) → optimistic removal on success
  "navigate" → useRouter().push(action.href)
```

---

## Page Layout Contract

```
apps/web/app/(main)/home/page.tsx
  └── HomeDashboard ("use client")
        ├── ConnectionStatusBanner (conditional)
        ├── WorkspaceSummary (grid row 1, full width)
        │   └── 4× MetricCard (responsive: 1→2→4 columns)
        ├── [grid row 2, 2 columns on lg+, stacked on sm]
        │   ├── RecentActivity (left column)
        │   └── PendingActions (right column)
        └── QuickActions (grid row 3, full width)

Responsive breakpoints:
  < 640px (sm): Single column, all sections stacked
  640–1023px: 2-column MetricCard grid; activity/pending stacked
  1024px+ (lg): 4-column MetricCard grid; activity + pending side-by-side
```
