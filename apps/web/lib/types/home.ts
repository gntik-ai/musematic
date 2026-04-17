export type HomeMetricId =
  | "active_agents"
  | "running_executions"
  | "pending_approvals"
  | "cost";

export interface MetricCardData {
  id: HomeMetricId;
  label: string;
  value: number | string;
  change:
    | {
        direction: "up" | "down" | "stable";
        delta: number | string;
      }
    | null;
  href?: string;
}

export interface WorkspaceSummaryResponse {
  workspace_id: string;
  active_agents: number;
  active_agents_change: number;
  running_executions: number;
  running_executions_change: number;
  pending_approvals: number;
  pending_approvals_change: number;
  cost_current: number;
  cost_previous: number;
  period_label: string;
}

export interface ActivityEntry {
  id: string;
  type: "interaction" | "execution";
  title: string;
  status: "running" | "completed" | "failed" | "canceled" | "waiting";
  timestamp: string;
  href: string;
  metadata?: {
    agent_fqn?: string;
    workflow_name?: string;
  };
}

export interface RecentActivityResponse {
  workspace_id: string;
  items: ActivityEntry[];
}

export type UrgencyLevel = "high" | "medium" | "low";

export interface PendingActionButton {
  id: string;
  label: string;
  variant: "default" | "destructive" | "ghost";
  action: "approve" | "reject" | "navigate";
  endpoint?: string;
  method?: "POST" | "DELETE";
}

export interface PendingAction {
  id: string;
  type: "approval" | "failed_execution" | "attention_request";
  title: string;
  description: string;
  urgency: UrgencyLevel;
  created_at: string;
  href: string;
  actions: PendingActionButton[];
}

export interface PendingActionsResponse {
  workspace_id: string;
  items: PendingAction[];
  total: number;
}

export interface QuickAction {
  id: string;
  label: string;
  icon: string;
  href: string;
  requiredPermission?: string;
}
