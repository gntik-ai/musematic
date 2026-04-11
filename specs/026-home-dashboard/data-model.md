# Data Model: Home Dashboard

**Branch**: `026-home-dashboard` | **Date**: 2026-04-11 | **Phase**: 1

This is a frontend-only feature. "Data model" captures TypeScript types, component prop interfaces, query key factories, and the Zustand store shape used by the dashboard. No new backend tables or migrations are required.

---

## TypeScript Types

```typescript
// apps/web/lib/types/home.ts

/** Workspace summary metric with change indicator */
export interface MetricCardData {
  id: "active_agents" | "running_executions" | "pending_approvals" | "cost";
  label: string;
  value: number | string;           // string for cost ("$142.50")
  change: {
    direction: "up" | "down" | "stable";
    delta: number | string;          // e.g., 2 or "+$12.30"
  } | null;
  href?: string;                     // Optional navigation target for the card
}

/** Workspace summary API response */
export interface WorkspaceSummaryResponse {
  workspace_id: string;
  active_agents: number;
  active_agents_change: number;       // delta from prior period (positive = increased)
  running_executions: number;
  running_executions_change: number;
  pending_approvals: number;
  pending_approvals_change: number;
  cost_current: number;               // current billing period cost in USD cents
  cost_previous: number;              // prior billing period cost in USD cents
  period_label: string;               // e.g., "Apr 2026"
}

/** Activity feed entry */
export interface ActivityEntry {
  id: string;
  type: "interaction" | "execution";
  title: string;                      // e.g., "Execution completed: daily-report-generator"
  status: "running" | "completed" | "failed" | "canceled" | "waiting";
  timestamp: string;                  // ISO 8601
  href: string;                       // Navigation target: /interactions/{id} or /executions/{id}
  metadata?: {
    agent_fqn?: string;               // For interactions
    workflow_name?: string;           // For executions
  };
}

/** Combined recent activity response */
export interface RecentActivityResponse {
  workspace_id: string;
  items: ActivityEntry[];             // Pre-sorted by timestamp desc, max 10
}

/** Pending action urgency levels */
export type UrgencyLevel = "high" | "medium" | "low";

/** A single pending action requiring user attention */
export interface PendingAction {
  id: string;
  type: "approval" | "failed_execution" | "attention_request";
  title: string;                      // e.g., "Approval required: policy-enforcement-agent"
  description: string;
  urgency: UrgencyLevel;
  created_at: string;                 // ISO 8601
  href: string;                       // Detail page link
  actions: PendingActionButton[];
}

/** Inline action button on a pending action card */
export interface PendingActionButton {
  id: string;
  label: string;                      // e.g., "Approve", "Reject", "View Details"
  variant: "default" | "destructive" | "ghost";
  action: "approve" | "reject" | "navigate";
  endpoint?: string;                  // API endpoint for approve/reject mutations
  method?: "POST" | "DELETE";
}

/** Combined pending actions response */
export interface PendingActionsResponse {
  workspace_id: string;
  items: PendingAction[];             // Pre-sorted by urgency (high → medium → low), then created_at desc
  total: number;
}

/** Quick action button */
export interface QuickAction {
  id: string;
  label: string;
  icon: string;                       // Lucide icon name
  href: string;
  requiredPermission?: string;        // e.g., "agents:write" — if present and user lacks it, button is disabled
}
```

---

## Query Key Factories

```typescript
// apps/web/lib/hooks/use-home-data.ts

export const homeQueryKeys = {
  all: (workspaceId: string) => ["home", workspaceId] as const,
  summary: (workspaceId: string) => ["home", workspaceId, "summary"] as const,
  activity: (workspaceId: string) => ["home", workspaceId, "activity"] as const,
  pendingActions: (workspaceId: string) => ["home", workspaceId, "pending-actions"] as const,
};
```

---

## Custom Hooks

```typescript
// apps/web/lib/hooks/use-home-data.ts

/** Workspace summary metrics */
export function useWorkspaceSummary(workspaceId: string) {
  return useQuery({
    queryKey: homeQueryKeys.summary(workspaceId),
    queryFn: () => api.get<WorkspaceSummaryResponse>(
      `/api/v1/workspaces/${workspaceId}/analytics/summary`
    ),
    staleTime: 30_000,
    refetchInterval: (data, query) =>
      query.state.fetchStatus === "idle" && !isWebSocketConnected ? 30_000 : false,
    enabled: !!workspaceId,
  });
}

/** Recent activity feed (top 10, pre-sorted by recency) */
export function useRecentActivity(workspaceId: string) {
  return useQuery({
    queryKey: homeQueryKeys.activity(workspaceId),
    queryFn: () => api.get<RecentActivityResponse>(
      `/api/v1/workspaces/${workspaceId}/dashboard/recent-activity`
    ),
    staleTime: 30_000,
    refetchInterval: (data, query) =>
      query.state.fetchStatus === "idle" && !isWebSocketConnected ? 30_000 : false,
    enabled: !!workspaceId,
  });
}

/** Pending actions (combined approvals + failed executions + attention) */
export function usePendingActions(workspaceId: string) {
  return useQuery({
    queryKey: homeQueryKeys.pendingActions(workspaceId),
    queryFn: () => api.get<PendingActionsResponse>(
      `/api/v1/workspaces/${workspaceId}/dashboard/pending-actions`
    ),
    staleTime: 30_000,
    enabled: !!workspaceId,
  });
}

/** Approve a pending action */
export function useApproveMutation(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ endpoint, method }: { endpoint: string; method: "POST" | "DELETE" }) =>
      api.request(method, endpoint),
    onMutate: async ({ endpoint }) => {
      // Optimistic update: remove the card immediately
      await queryClient.cancelQueries({ queryKey: homeQueryKeys.pendingActions(workspaceId) });
      const previous = queryClient.getQueryData(homeQueryKeys.pendingActions(workspaceId));
      queryClient.setQueryData(homeQueryKeys.pendingActions(workspaceId), (old: PendingActionsResponse) => ({
        ...old,
        items: old.items.filter(item => !item.actions.some(a => a.endpoint === endpoint)),
      }));
      return { previous };
    },
    onError: (err, variables, context) => {
      queryClient.setQueryData(homeQueryKeys.pendingActions(workspaceId), context?.previous);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: homeQueryKeys.pendingActions(workspaceId) });
      queryClient.invalidateQueries({ queryKey: homeQueryKeys.summary(workspaceId) });
    },
  });
}

/** WebSocket connection status hook */
export function useWebSocketStatus(): { isConnected: boolean } {
  const [isConnected, setIsConnected] = useState(true);
  useEffect(() => {
    const unsubscribe = wsClient.onConnectionChange(setIsConnected);
    return unsubscribe;
  }, []);
  return { isConnected };
}

/** Dashboard WebSocket subscription — invalidates queries on relevant events */
export function useDashboardWebSocket(workspaceId: string) {
  const queryClient = useQueryClient();
  useEffect(() => {
    const channels = ["execution", "interaction", "workspace"];
    const unsubscribers = channels.map(channel =>
      wsClient.subscribe(channel, (event) => {
        // Invalidate relevant query based on event type
        if (event.type.startsWith("execution")) {
          queryClient.invalidateQueries({ queryKey: homeQueryKeys.activity(workspaceId) });
          queryClient.invalidateQueries({ queryKey: homeQueryKeys.summary(workspaceId) });
          if (["execution.failed", "execution.requires_approval"].includes(event.type)) {
            queryClient.invalidateQueries({ queryKey: homeQueryKeys.pendingActions(workspaceId) });
          }
        }
        if (event.type.startsWith("interaction")) {
          queryClient.invalidateQueries({ queryKey: homeQueryKeys.activity(workspaceId) });
        }
        if (["workspace.approval.created", "interaction.attention.requested"].includes(event.type)) {
          queryClient.invalidateQueries({ queryKey: homeQueryKeys.pendingActions(workspaceId) });
          queryClient.invalidateQueries({ queryKey: homeQueryKeys.summary(workspaceId) });
        }
      })
    );
    return () => unsubscribers.forEach(u => u());
  }, [workspaceId, queryClient]);
}
```

---

## Component Props

```typescript
// apps/web/components/features/home/WorkspaceSummary.tsx
interface WorkspaceSummaryProps {
  workspaceId: string;
}

// apps/web/components/features/home/RecentActivity.tsx
interface RecentActivityProps {
  workspaceId: string;
}

// apps/web/components/features/home/PendingActions.tsx
interface PendingActionsProps {
  workspaceId: string;
}

// apps/web/components/features/home/QuickActions.tsx
interface QuickActionsProps {
  // No props needed — quick actions are static + use workspace context from store
}

// apps/web/components/features/home/ConnectionStatusBanner.tsx
interface ConnectionStatusBannerProps {
  isConnected: boolean;
}

// apps/web/components/features/home/PendingActionCard.tsx
interface PendingActionCardProps {
  action: PendingAction;
  workspaceId: string;
  onActionComplete?: () => void;
}
```

---

## Quick Actions Configuration

```typescript
// apps/web/components/features/home/QuickActions.tsx

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: "new-conversation",
    label: "New Conversation",
    icon: "MessageSquarePlus",
    href: "/conversations/new",
    // No permission required — all roles can start conversations
  },
  {
    id: "upload-agent",
    label: "Upload Agent",
    icon: "Bot",
    href: "/registry/upload",
    requiredPermission: "agents:write",
  },
  {
    id: "create-workflow",
    label: "Create Workflow",
    icon: "GitBranch",
    href: "/workflows/new",
    requiredPermission: "workflows:write",
  },
  {
    id: "browse-marketplace",
    label: "Browse Marketplace",
    icon: "Store",
    href: "/marketplace",
    // No permission required — all roles can browse
  },
];
```

---

## Static Data (No Backend Required)

Quick actions configuration is static (no API call needed). The `requiredPermission` field is checked against the user's workspace role from the existing auth store.
