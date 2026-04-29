import type { Page } from "@playwright/test";

const operatorMetrics = {
  activeExecutions: 12,
  queuedSteps: 41,
  pendingApprovals: 3,
  recentFailures: 2,
  avgLatencyMs: 842,
  fleetHealthScore: 91,
  computedAt: "2026-04-16T11:59:45.000Z",
};

const serviceHealth = {
  status: "degraded",
  uptime_seconds: 86400,
  dependencies: {
    postgresql: { status: "healthy", latency_ms: 14 },
    redis: { status: "healthy", latency_ms: 4 },
    kafka: { status: "degraded", latency_ms: 88 },
    qdrant: { status: "healthy", latency_ms: 22 },
    neo4j: { status: "unhealthy", latency_ms: 140 },
    clickhouse: { status: "healthy", latency_ms: 36 },
    opensearch: { status: "unknown", latency_ms: null },
    minio: { status: "healthy", latency_ms: 19 },
    runtime_controller: { status: "healthy", latency_ms: 29 },
    reasoning_engine: { status: "degraded", latency_ms: 130 },
    sandbox_manager: { status: "healthy", latency_ms: 31 },
    simulation_controller: { status: "healthy", latency_ms: 27 },
  },
};

const activeExecutions = [
  {
    id: "exec-run-0001",
    workflowName: "Fraud triage",
    workflow_name: "Fraud triage",
    agentFqn: "risk:triage-lead",
    agent_fqn: "risk:triage-lead",
    currentStepLabel: "Assess evidence",
    current_step_label: "Assess evidence",
    status: "running",
    startedAt: "2026-04-16T11:58:00.000Z",
    started_at: "2026-04-16T11:58:00.000Z",
  },
  {
    id: "exec-pause-0002",
    workflowName: "Identity review",
    workflow_name: "Identity review",
    agentFqn: "risk:identity-analyst",
    agent_fqn: "risk:identity-analyst",
    currentStepLabel: null,
    current_step_label: null,
    status: "paused",
    startedAt: "2026-04-16T11:55:00.000Z",
    started_at: "2026-04-16T11:55:00.000Z",
  },
  {
    id: "exec-approval-0003",
    workflowName: "Chargeback recovery",
    workflow_name: "Chargeback recovery",
    agentFqn: "risk:chargeback-bot",
    agent_fqn: "risk:chargeback-bot",
    currentStepLabel: "Await legal review",
    current_step_label: "Await legal review",
    status: "waiting_for_approval",
    startedAt: "2026-04-16T11:59:00.000Z",
    started_at: "2026-04-16T11:59:00.000Z",
  },
] as const;

const attentionEvents = [
  {
    id: "attention-1",
    source_agent_fqn: "risk:fraud-monitor",
    urgency: "critical",
    context_summary: "Manual adjudication required for high-value fraud cluster.",
    target_type: "execution",
    target_id: "exec-run-0001",
    status: "pending",
    created_at: "2026-04-16T12:00:00.000Z",
  },
  {
    id: "attention-2",
    source_agent_fqn: "risk:conversation-bot",
    urgency: "medium",
    context_summary: "Customer conversation needs escalation to a human reviewer.",
    target_type: "interaction",
    target_id: "conv-22",
    status: "pending",
    created_at: "2026-04-16T11:59:00.000Z",
  },
] as const;

const queueLag = {
  topics: [
    { topic: "orchestration.primary", lag: 14872, warning: true },
    { topic: "attention.requests", lag: 220, warning: false },
    { topic: "reasoning.telemetry", lag: 840, warning: false },
  ],
  computed_at: "2026-04-16T12:00:00.000Z",
};

const reasoningBudget = {
  total_capacity_tokens: 1000000,
  used_tokens: 950000,
  utilization_pct: 95,
  active_execution_count: 12,
  critical_pressure: true,
  computed_at: "2026-04-16T12:00:00.000Z",
};

const regionRows = [
  {
    id: "region-primary",
    region_code: "eu-west",
    region_role: "primary",
    endpoint_urls: {},
    rpo_target_minutes: 5,
    rto_target_minutes: 30,
    enabled: true,
    created_at: "2026-04-16T10:00:00.000Z",
    updated_at: "2026-04-16T10:00:00.000Z",
  },
  {
    id: "region-secondary",
    region_code: "us-east",
    region_role: "secondary",
    endpoint_urls: {},
    rpo_target_minutes: 5,
    rto_target_minutes: 30,
    enabled: true,
    created_at: "2026-04-16T10:00:00.000Z",
    updated_at: "2026-04-16T10:00:00.000Z",
  },
] as const;

const replicationStatus = {
  generated_at: "2026-04-16T12:00:00.000Z",
  items: [
    {
      id: "replication-postgres",
      source_region: "eu-west",
      target_region: "us-east",
      component: "postgres",
      lag_seconds: 12,
      health: "healthy",
      pause_reason: null,
      error_detail: null,
      measured_at: "2026-04-16T12:00:00.000Z",
      threshold_seconds: 300,
      missing_probe: false,
    },
    {
      id: "replication-kafka",
      source_region: "eu-west",
      target_region: "us-east",
      component: "kafka",
      lag_seconds: 70,
      health: "degraded",
      pause_reason: null,
      error_detail: null,
      measured_at: "2026-04-16T12:00:00.000Z",
      threshold_seconds: 300,
      missing_probe: false,
    },
  ],
};

const failoverPlan = {
  id: "plan-primary-dr",
  name: "primary-to-dr",
  from_region: "eu-west",
  to_region: "us-east",
  steps: [{ kind: "custom", name: "Operator verification", parameters: {} }],
  runbook_url: "/docs/runbooks/failover.md",
  tested_at: "2026-04-01T10:00:00.000Z",
  last_executed_at: null,
  created_by: null,
  version: 1,
  created_at: "2026-04-01T09:00:00.000Z",
  updated_at: "2026-04-01T09:00:00.000Z",
  is_stale: false,
};

const capacitySignals = [
  {
    resource_class: "compute",
    historical_trend: [
      { period: "day-1", utilization: 62 },
      { period: "day-2", utilization: 72 },
    ],
    projection: { projected_utilization: 0.84 },
    saturation_horizon: { threshold: 0.8, horizon_days: 7 },
    confidence: "ok",
    recommendation: {
      action: "Review capacity and cost forecast",
      link: "/costs",
      reason: "Compute capacity is projected above the configured horizon.",
    },
    generated_at: "2026-04-16T12:00:00.000Z",
  },
];

const reasoningTrace = {
  execution_id: "exec-run-0001",
  total_tokens: 3820,
  total_duration_ms: 1820,
  steps: [
    {
      id: "step-1",
      mode: "reflection",
      input_summary: "Review the latest fraud signals and supporting evidence.",
      output_summary:
        "Initial adjudication identified a high-confidence fraud cluster.",
      full_output_ref:
        "Full output trace for step 1: confidence 0.92 with a two-hop entity match.",
      token_count: 1400,
      duration_ms: 620,
      self_corrections: [
        {
          iteration_index: 1,
          original_output_summary:
            "Original output over-weighted a stale device fingerprint.",
          correction_reason:
            "Device graph data was older than the freshness threshold.",
          corrected_output_summary:
            "Recomputed score after removing stale device evidence.",
          token_delta: 84,
        },
      ],
    },
    {
      id: "step-2",
      mode: "react",
      input_summary: "Cross-check the recommendation against policy constraints.",
      output_summary: "Policy alignment confirmed and escalation prepared.",
      full_output_ref: null,
      token_count: 1120,
      duration_ms: 540,
      self_corrections: [],
    },
  ],
};

const contextQuality = {
  overall_quality_score: 84,
  assembled_at: "2026-04-16T12:00:00.000Z",
  sources: [
    {
      id: "source-1",
      source_type: "memory",
      quality_score: 92,
      contribution_weight: 0.45,
      provenance_ref: "https://musematic.dev/memory/123",
    },
    {
      id: "source-2",
      source_type: "knowledge_graph",
      quality_score: 78,
      contribution_weight: 0.35,
      provenance_ref: "https://musematic.dev/kg/456",
    },
  ],
};

const budgetStatus = {
  execution_id: "exec-run-0001",
  is_active: true,
  computed_at: "2026-04-16T12:00:00.000Z",
  dimensions: [
    {
      dimension: "tokens",
      label: "Tokens",
      used: 4200,
      limit: 10000,
      unit: "tokens",
      utilization_pct: 42,
      near_limit: false,
    },
    {
      dimension: "tool_invocations",
      label: "Tool invocations",
      used: 14,
      limit: 20,
      unit: "calls",
      utilization_pct: 70,
      near_limit: true,
    },
    {
      dimension: "memory_writes",
      label: "Memory writes",
      used: 19,
      limit: 20,
      unit: "writes",
      utilization_pct: 95,
      near_limit: true,
    },
    {
      dimension: "elapsed_time",
      label: "Elapsed time",
      used: 1820,
      limit: 5000,
      unit: "ms",
      utilization_pct: 36.4,
      near_limit: false,
    },
  ],
};

function matchCsv(filterValue: string, candidate: string): boolean {
  if (!filterValue) {
    return true;
  }

  return filterValue.split(",").includes(candidate);
}

export async function installOperatorState(page: Page) {
  await page.addInitScript(() => {
    type OperatorMessage = {
      channel: string;
      type: string;
      payload: unknown;
      timestamp?: string;
    };

    const sockets: MockWebSocket[] = [];

    class MockWebSocket extends EventTarget {
      static OPEN = 1;
      readyState = 1;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;

      constructor() {
        super();
        sockets.push(this);
        window.setTimeout(() => {
          const event = new Event("open");
          this.onopen?.(event);
          this.dispatchEvent(event);
        }, 0);
      }

      close() {
        const event = new CloseEvent("close");
        this.onclose?.(event);
        this.dispatchEvent(event);
      }

      send(message: string) {
        void message;
      }
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });

    Object.defineProperty(window, "__emitOperatorEvent", {
      configurable: true,
      writable: true,
      value: (message: OperatorMessage) => {
        const event = new MessageEvent("message", {
          data: JSON.stringify(message),
        });

        sockets.forEach((socket) => {
          socket.onmessage?.(event);
          socket.dispatchEvent(event);
        });
      },
    });

    localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: {
            id: "user-1",
            email: "operator@musematic.dev",
            displayName: "Operator",
            avatarUrl: null,
            roles: ["superadmin", "platform_admin", "workspace_admin"],
            workspaceId: "workspace-1",
            mfaEnrolled: true,
          },
          accessToken: "mock-access-token",
          refreshToken: "mock-refresh-token",
          isAuthenticated: true,
          isLoading: false,
        },
        version: 0,
      }),
    );

    localStorage.setItem(
      "workspace-storage",
      JSON.stringify({
        state: {
          currentWorkspace: {
            id: "workspace-1",
            name: "Risk Ops",
            slug: "risk-ops",
            description: "Risk operations workspace",
            memberCount: 8,
            createdAt: "2026-04-10T09:00:00.000Z",
          },
          sidebarCollapsed: false,
        },
        version: 0,
      }),
    );
  });
}

export async function mockOperatorApi(page: Page) {
  let maintenanceWindow = {
    id: "window-planned",
    starts_at: "2099-01-01T01:00:00.000Z",
    ends_at: "2099-01-01T02:00:00.000Z",
    reason: "database maintenance",
    blocks_writes: true,
    announcement_text: "Writes are paused for maintenance",
    status: "scheduled",
    scheduled_by: null,
    enabled_at: null as string | null,
    disabled_at: null as string | null,
    disable_failure_reason: null,
    created_at: "2026-04-16T12:00:00.000Z",
    updated_at: "2026-04-16T12:00:00.000Z",
  };
  let maintenanceActive = false;
  const failoverRuns = [
    {
      id: "run-initial",
      plan_id: failoverPlan.id,
      run_kind: "rehearsal",
      outcome: "succeeded",
      started_at: "2026-04-01T10:00:00.000Z",
      ended_at: "2026-04-01T10:01:00.000Z",
      step_outcomes: [
        {
          step_index: 0,
          kind: "custom",
          name: "Operator verification",
          outcome: "succeeded",
          duration_ms: 120,
          error_detail: null,
        },
      ],
      initiated_by: null,
      reason: "quarterly",
    },
  ];

  await page.route("**/api/v1/regions", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(regionRows),
      status: 200,
    });
  });

  await page.route("**/api/v1/regions/replication-status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(replicationStatus),
      status: 200,
    });
  });

  await page.route("**/api/v1/regions/failover-plans", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([failoverPlan]),
      status: 200,
    });
  });

  await page.route("**/api/v1/regions/failover-plans/plan-primary-dr/runs", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(failoverRuns),
      status: 200,
    });
  });

  await page.route(
    "**/api/v1/admin/regions/failover-plans/plan-primary-dr/rehearse",
    async (route) => {
      const run = {
        id: `run-${failoverRuns.length + 1}`,
        plan_id: failoverPlan.id,
        run_kind: "rehearsal",
        outcome: "succeeded",
        started_at: "2026-04-16T12:00:00.000Z",
        ended_at: "2026-04-16T12:01:00.000Z",
        step_outcomes: [
          {
            step_index: 0,
            kind: "custom",
            name: "Operator verification",
            outcome: "succeeded",
            duration_ms: 120,
            error_detail: null,
          },
        ],
        initiated_by: null,
        reason: "manual rehearsal",
      };
      failoverRuns.unshift(run);
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(run),
        status: 200,
      });
    },
  );

  await page.route("**/api/v1/regions/upgrade-status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        runtime_versions: [
          {
            runtime_id: "python-worker",
            version: "2026.04.1",
            status: "serving",
            coexistence_until: "2026-05-01T00:00:00.000Z",
          },
        ],
        documentation_links: {},
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/maintenance/windows", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([maintenanceWindow]),
      status: 200,
    });
  });

  await page.route("**/api/v1/maintenance/windows/active", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(maintenanceActive ? maintenanceWindow : null),
      status: 200,
    });
  });

  await page.route("**/api/v1/admin/maintenance/windows", async (route) => {
    let payload: Record<string, unknown> | null = null;
    try {
      payload = route.request().postDataJSON() as Record<string, unknown>;
    } catch {
      payload = null;
    }
    maintenanceWindow = {
      ...maintenanceWindow,
      id: "window-scheduled",
      starts_at: String(payload?.starts_at ?? maintenanceWindow.starts_at),
      ends_at: String(payload?.ends_at ?? maintenanceWindow.ends_at),
      reason: String(payload?.reason ?? maintenanceWindow.reason),
      announcement_text: String(payload?.announcement_text ?? maintenanceWindow.announcement_text),
      status: "scheduled",
    };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(maintenanceWindow),
      status: 201,
    });
  });

  await page.route("**/api/v1/admin/maintenance/windows/*/enable", async (route) => {
    maintenanceActive = true;
    maintenanceWindow = {
      ...maintenanceWindow,
      status: "active",
      enabled_at: "2026-04-16T12:01:00.000Z",
    };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(maintenanceWindow),
      status: 200,
    });
  });

  await page.route("**/api/v1/admin/maintenance/windows/*/disable", async (route) => {
    maintenanceActive = false;
    maintenanceWindow = {
      ...maintenanceWindow,
      status: "completed",
      disabled_at: "2026-04-16T12:02:00.000Z",
    };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(maintenanceWindow),
      status: 200,
    });
  });

  await page.route("**/api/v1/regions/capacity?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(capacitySignals),
      status: 200,
    });
  });

  await page.route("**/api/v1/admin/regions", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        maintenanceActive
          ? {
              error: "maintenance_in_progress",
              announcement: maintenanceWindow.announcement_text,
            }
          : { status: "created" },
      ),
      status: maintenanceActive ? 503 : 200,
    });
  });

  await page.route("**/api/v1/dashboard/metrics", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(operatorMetrics),
      status: 200,
    });
  });

  await page.route("**/health", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(serviceHealth),
      status: 200,
    });
  });

  await page.route("**/api/v1/executions?**", async (route) => {
    const url = new URL(route.request().url());
    const status = url.searchParams.get("status") ?? "";
    const sortBy = url.searchParams.get("sort_by") ?? "started_at";

    const filtered = activeExecutions
      .filter((execution) => matchCsv(status, execution.status))
      .sort((left, right) => {
        if (sortBy === "elapsed") {
          return (
            new Date(left.started_at).getTime() -
            new Date(right.started_at).getTime()
          );
        }

        return (
          new Date(right.started_at).getTime() -
          new Date(left.started_at).getTime()
        );
      });

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: filtered,
        total: filtered.length,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/interactions/attention?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: attentionEvents,
        total: attentionEvents.length,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/dashboard/queue-lag", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(queueLag),
      status: 200,
    });
  });

  await page.route(
    "**/api/v1/dashboard/reasoning-budget-utilization",
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(reasoningBudget),
        status: 200,
      });
    },
  );

  await page.route("**/api/v1/executions/exec-run-0001/reasoning-trace", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(reasoningTrace),
      status: 200,
    });
  });

  await page.route("**/api/v1/executions/exec-run-0001/context-quality", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(contextQuality),
      status: 200,
    });
  });

  await page.route("**/api/v1/executions/exec-run-0001/budget-status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(budgetStatus),
      status: 200,
    });
  });

  await page.route("**/api/v1/executions/exec-run-0001", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(activeExecutions[0]),
      status: 200,
    });
  });
}

export async function emitOperatorAlert(page: Page) {
  await page.evaluate(() => {
    (
      window as typeof window & {
        __emitOperatorEvent: (message: {
          channel: string;
          type: string;
          payload: unknown;
          timestamp?: string;
        }) => void;
      }
    ).__emitOperatorEvent({
      channel: "alerts",
      type: "event",
      timestamp: "2026-04-16T12:00:01.000Z",
      payload: {
        id: "alert-1",
        severity: "critical",
        source_service: "runtime-controller",
        message: "Execution admission paused.",
        description:
          "The runtime controller rejected new workloads after repeated faults.",
        suggested_action:
          "Review the most recent deployment and drain the queue.",
      },
    });
  });
}
