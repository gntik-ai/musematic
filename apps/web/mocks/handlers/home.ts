import { http, HttpResponse } from "msw";
import type {
  PendingAction,
  PendingActionsResponse,
  RecentActivityResponse,
  WorkspaceSummaryResponse,
} from "@/lib/types/home";

function iso(minutesAgo: number): string {
  return new Date(Date.now() - minutesAgo * 60_000).toISOString();
}

function buildSummary(workspaceId: string): WorkspaceSummaryResponse {
  return {
    workspace_id: workspaceId,
    active_agents: workspaceId === "workspace-2" ? 7 : 12,
    active_agents_change: workspaceId === "workspace-2" ? -1 : 3,
    running_executions: workspaceId === "workspace-2" ? 2 : 4,
    running_executions_change: workspaceId === "workspace-2" ? 1 : 0,
    pending_approvals: workspaceId === "workspace-2" ? 1 : 2,
    pending_approvals_change: workspaceId === "workspace-2" ? 1 : -1,
    cost_current: workspaceId === "workspace-2" ? 86_40 : 142_50,
    cost_previous: workspaceId === "workspace-2" ? 82_10 : 130_20,
    period_label: "Apr 2026",
  };
}

function buildRecentActivity(workspaceId: string): RecentActivityResponse {
  return {
    workspace_id: workspaceId,
    items: [
      {
        id: `${workspaceId}-execution-1`,
        type: "execution",
        title: "Execution completed: daily-report-generator",
        status: "completed",
        timestamp: iso(4),
        href: "/executions/execution-1",
        metadata: {
          workflow_name: "Daily report generator",
        },
      },
      {
        id: `${workspaceId}-interaction-1`,
        type: "interaction",
        title: "Attention requested: policy-enforcement-agent",
        status: "waiting",
        timestamp: iso(12),
        href: "/interactions/interaction-1",
        metadata: {
          agent_fqn: "ops:policy-enforcement-agent",
        },
      },
      {
        id: `${workspaceId}-execution-2`,
        type: "execution",
        title: "Execution failed: customer-escalation-triage",
        status: "failed",
        timestamp: iso(26),
        href: "/executions/execution-2",
        metadata: {
          workflow_name: "Customer escalation triage",
        },
      },
    ],
  };
}

function buildPendingActions(workspaceId: string): PendingActionsResponse {
  const basePath = `/api/v1/workspaces/${workspaceId}/approvals`;
  const items: PendingAction[] = [
    {
      id: `${workspaceId}-failed-execution`,
      type: "failed_execution",
      title: "Execution failed: runtime-sandbox-healthcheck",
      description: "The latest execution exhausted retries and needs operator attention.",
      urgency: "high",
      created_at: iso(7),
      href: "/executions/execution-failed-1",
      actions: [
        {
          id: "review-failure",
          label: "View Details",
          variant: "ghost",
          action: "navigate",
        },
      ],
    },
    {
      id: `${workspaceId}-approval-1`,
      type: "approval",
      title: "Approval required: policy-enforcement-agent",
      description: "A protected execution is waiting for a workspace admin decision.",
      urgency: "medium",
      created_at: iso(18),
      href: "/executions/approval-1",
      actions: [
        {
          id: "approve-1",
          label: "Approve",
          variant: "default",
          action: "approve",
          endpoint: `${basePath}/approval-1/approve`,
          method: "POST",
        },
        {
          id: "reject-1",
          label: "Reject",
          variant: "destructive",
          action: "reject",
          endpoint: `${basePath}/approval-1/reject`,
          method: "POST",
        },
      ],
    },
    {
      id: `${workspaceId}-attention-1`,
      type: "attention_request",
      title: "Agent attention requested: trust-escalation-monitor",
      description: "A conversation asked for immediate trust officer review.",
      urgency: "low",
      created_at: iso(33),
      href: "/interactions/attention-1",
      actions: [
        {
          id: "open-thread",
          label: "Open Thread",
          variant: "ghost",
          action: "navigate",
        },
      ],
    },
  ];

  return {
    workspace_id: workspaceId,
    items,
    total: items.length,
  };
}

export interface HomeMockState {
  summaryByWorkspace: Record<string, WorkspaceSummaryResponse>;
  activityByWorkspace: Record<string, RecentActivityResponse>;
  pendingByWorkspace: Record<string, PendingActionsResponse>;
}

export function createHomeMockState(): HomeMockState {
  return {
    summaryByWorkspace: {
      "workspace-1": buildSummary("workspace-1"),
      "workspace-2": buildSummary("workspace-2"),
    },
    activityByWorkspace: {
      "workspace-1": buildRecentActivity("workspace-1"),
      "workspace-2": buildRecentActivity("workspace-2"),
    },
    pendingByWorkspace: {
      "workspace-1": buildPendingActions("workspace-1"),
      "workspace-2": buildPendingActions("workspace-2"),
    },
  };
}

export const homeFixtures: HomeMockState = createHomeMockState();

export function resetHomeFixtures(): void {
  const fresh = createHomeMockState();
  homeFixtures.summaryByWorkspace = fresh.summaryByWorkspace;
  homeFixtures.activityByWorkspace = fresh.activityByWorkspace;
  homeFixtures.pendingByWorkspace = fresh.pendingByWorkspace;
}

export const homeHandlers = [
  http.get("*/api/v1/workspaces/:workspaceId/analytics/summary", ({ params }) => {
    const workspaceId = String(params.workspaceId);
    const payload = homeFixtures.summaryByWorkspace[workspaceId] ?? buildSummary(workspaceId);
    homeFixtures.summaryByWorkspace[workspaceId] = payload;
    return HttpResponse.json(payload);
  }),
  http.get("*/api/v1/workspaces/:workspaceId/dashboard/recent-activity", ({ params }) => {
    const workspaceId = String(params.workspaceId);
    const payload =
      homeFixtures.activityByWorkspace[workspaceId] ?? buildRecentActivity(workspaceId);
    homeFixtures.activityByWorkspace[workspaceId] = payload;
    return HttpResponse.json(payload);
  }),
  http.get("*/api/v1/workspaces/:workspaceId/dashboard/pending-actions", ({ params }) => {
    const workspaceId = String(params.workspaceId);
    const payload =
      homeFixtures.pendingByWorkspace[workspaceId] ?? buildPendingActions(workspaceId);
    homeFixtures.pendingByWorkspace[workspaceId] = payload;
    return HttpResponse.json(payload);
  }),
  http.post(
    "*/api/v1/workspaces/:workspaceId/approvals/:approvalId/approve",
    ({ params }) => {
      const workspaceId = String(params.workspaceId);
      const approvalId = String(params.approvalId);
      const pending = homeFixtures.pendingByWorkspace[workspaceId];
      if (pending) {
        const nextItems = pending.items.filter(
          (item) => item.id !== `${workspaceId}-${approvalId}`,
        );
        homeFixtures.pendingByWorkspace[workspaceId] = {
          ...pending,
          items: nextItems,
          total: nextItems.length,
        };
      }
      return HttpResponse.json({ approved: true });
    },
  ),
  http.post(
    "*/api/v1/workspaces/:workspaceId/approvals/:approvalId/reject",
    ({ params }) => {
      const workspaceId = String(params.workspaceId);
      const approvalId = String(params.approvalId);
      const pending = homeFixtures.pendingByWorkspace[workspaceId];
      if (pending) {
        const nextItems = pending.items.filter(
          (item) => item.id !== `${workspaceId}-${approvalId}`,
        );
        homeFixtures.pendingByWorkspace[workspaceId] = {
          ...pending,
          items: nextItems,
          total: nextItems.length,
        };
      }
      return HttpResponse.json({ rejected: true });
    },
  ),
];
