import { http, HttpResponse } from "msw";

const now = "2026-04-20T10:00:00.000Z";

const rubric = {
  id: "rubric-1",
  name: "Trajectory quality rubric",
  description: "Score the trajectory.",
  criteria: [
    { name: "Accuracy", description: "Correctness", weight: 0.5, scale_max: 5 },
    { name: "Fluency", description: "Clarity", weight: 0.3, scale_max: 5 },
    { name: "Safety", description: "Risk handling", weight: 0.2, scale_max: 5 },
  ],
};

const evalSet = {
  id: "suite-1",
  name: "Trajectory Suite",
  scorer_config: {
    llm_judge: {
      enabled: true,
      rubric_id: rubric.id,
      calibration_run_id: "calibration-1",
    },
    trajectory_comparison: {
      method: "exact_match",
    },
  },
};

const calibrationRun = {
  id: "calibration-1",
  agreement_rate: 0.52,
  distribution: {
    dimensions: [
      {
        dimension_id: "safety",
        dimension_name: "Safety",
        kappa: 0.52,
        distribution: { min: 1, q1: 2, median: 3, q3: 4, max: 5 },
      },
    ],
  },
};

const contracts = [
  {
    id: "contract-1",
    agent_id: "risk:kyc-monitor",
    task_scope: "Version one excerpt",
    is_archived: true,
    created_at: "2026-04-10T00:00:00.000Z",
    updated_at: "2026-04-11T00:00:00.000Z",
  },
  {
    id: "contract-2",
    agent_id: "risk:kyc-monitor",
    task_scope: "Version two excerpt",
    is_archived: true,
    created_at: "2026-04-12T00:00:00.000Z",
    updated_at: "2026-04-13T00:00:00.000Z",
  },
  {
    id: "contract-3",
    agent_id: "risk:kyc-monitor",
    task_scope: "Version three excerpt",
    is_archived: false,
    created_at: "2026-04-14T00:00:00.000Z",
    updated_at: "2026-04-14T00:00:00.000Z",
  },
];

const mcpServers = [
  {
    server_id: "server-1",
    display_name: "Compliance MCP",
    endpoint_url: "https://mcp.musematic.dev",
    tool_count: 4,
    status: "healthy",
    health: {
      status: "healthy",
      last_success_at: now,
    },
  },
];

const certifiers = [
  {
    id: "certifier-1",
    name: "Trust Board",
    permitted_scopes: ["global"],
    credentials: {
      endpoint: "https://certifier.musematic.dev",
      public_key_fingerprint: "fingerprint-1",
    },
  },
];

const surveillanceSignals = [
  {
    id: "signal-1",
    agent_id: "risk:fraud-monitor",
    signal_type: "execution_quality",
    score_contribution: 0.91,
    created_at: now,
    source_type: "Fraud monitor is stable",
  },
  {
    id: "signal-2",
    agent_id: "risk:kyc-review",
    signal_type: "policy_drift",
    score_contribution: 0.31,
    created_at: now,
    source_type: "KYC review drift detected",
  },
];

const governanceChain = {
  id: "chain-1",
  workspace_id: "workspace-1",
  observer_fqns: ["ops:observer"],
  judge_fqns: ["ops:judge"],
  enforcer_fqns: ["ops:enforcer"],
  created_at: now,
};

const visibilityState = {
  workspace_id: "workspace-1",
  visibility_agents: ["ops:*", "risk:*"],
  visibility_tools: [],
  updated_at: now,
};

const alertRules = {
  items: [
    {
      id: "rule-1",
      transition_type: "interaction.idle",
      delivery_method: "in_app",
      enabled: true,
      interaction_id: null,
    },
  ],
};

const unreadCount = { count: 2 };

export function resetFrontendExpansionFixtures() {
  rubric.name = "Trajectory quality rubric";
  rubric.description = "Score the trajectory.";
  rubric.criteria = [
    { name: "Accuracy", description: "Correctness", weight: 0.5, scale_max: 5 },
    { name: "Fluency", description: "Clarity", weight: 0.3, scale_max: 5 },
    { name: "Safety", description: "Risk handling", weight: 0.2, scale_max: 5 },
  ];
  evalSet.scorer_config.trajectory_comparison.method = "exact_match";
  while (certifiers.length > 1) certifiers.pop();
  while (mcpServers.length > 1) mcpServers.pop();
}

export const frontendExpansionHandlers = [
  http.get("*/api/v1/evaluations/eval-sets/:suiteId", ({ params }) => {
    return HttpResponse.json({ ...evalSet, id: String(params.suiteId) });
  }),
  http.patch("*/api/v1/evaluations/eval-sets/:suiteId", async ({ params, request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    evalSet.scorer_config = (body.scorer_config as typeof evalSet.scorer_config) ?? evalSet.scorer_config;
    return HttpResponse.json({ ...evalSet, id: String(params.suiteId) });
  }),
  http.get("*/api/v1/evaluations/rubrics/:rubricId", ({ params }) => {
    return HttpResponse.json({ ...rubric, id: String(params.rubricId) });
  }),
  http.post("*/api/v1/evaluations/rubrics", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    rubric.name = String(body.name ?? rubric.name);
    rubric.description = String(body.description ?? rubric.description);
    rubric.criteria = Array.isArray(body.criteria) ? (body.criteria as typeof rubric.criteria) : rubric.criteria;
    return HttpResponse.json(rubric, { status: 201 });
  }),
  http.patch("*/api/v1/evaluations/rubrics/:rubricId", async ({ params, request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    rubric.name = String(body.name ?? rubric.name);
    rubric.description = String(body.description ?? rubric.description);
    rubric.criteria = Array.isArray(body.criteria) ? (body.criteria as typeof rubric.criteria) : rubric.criteria;
    return HttpResponse.json({ ...rubric, id: String(params.rubricId) });
  }),
  http.get("*/api/v1/evaluations/calibration-runs/:runId", ({ params }) => {
    return HttpResponse.json({ ...calibrationRun, id: String(params.runId) });
  }),
  http.get("*/api/v1/trust/contracts", ({ request }) => {
    const url = new URL(request.url);
    const agentId = url.searchParams.get("agent_id");
    const items = agentId ? contracts.filter((item) => item.agent_id === agentId) : contracts;
    return HttpResponse.json({ items, total: items.length });
  }),
  http.delete("*/api/v1/trust/contracts/:contractId", ({ params }) => {
    const index = contracts.findIndex((item) => item.id === String(params.contractId));
    if (index >= 0) {
      contracts.splice(index, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("*/.well-known/agent.json", () => {
    return HttpResponse.json({ agent: "risk:kyc-monitor", skills: ["audit"] });
  }),
  http.get("*/api/v1/mcp/servers", () => {
    return HttpResponse.json({ items: mcpServers, total: mcpServers.length });
  }),
  http.delete("*/api/v1/mcp/servers/:serverId", ({ params }) => {
    const index = mcpServers.findIndex((item) => item.server_id === String(params.serverId));
    if (index >= 0) {
      mcpServers.splice(index, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("*/api/v1/trust/certifiers", () => {
    return HttpResponse.json({ items: certifiers, total: certifiers.length });
  }),
  http.post("*/api/v1/trust/certifiers", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    const created = {
      id: `certifier-${certifiers.length + 1}`,
      name: String(body.name ?? "New Certifier"),
      permitted_scopes: Array.isArray(body.permitted_scopes) ? body.permitted_scopes.map(String) : ["global"],
      credentials: {
        endpoint: String((body.credentials as Record<string, unknown> | undefined)?.endpoint ?? "https://example.invalid"),
        public_key_fingerprint: String((body.credentials as Record<string, unknown> | undefined)?.public_key_fingerprint ?? "fingerprint-new"),
      },
    };
    certifiers.push(created);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.delete("*/api/v1/trust/certifiers/:certifierId", ({ params }) => {
    const index = certifiers.findIndex((item) => item.id === String(params.certifierId));
    if (index >= 0) {
      certifiers.splice(index, 1);
    }
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("*/api/v1/trust/agents/:agentId/signals", ({ params }) => {
    const items = surveillanceSignals.filter((item) => item.agent_id === String(params.agentId)).slice(0, 20);
    return HttpResponse.json({ items, total: items.length });
  }),
  http.get("*/api/v1/workspaces/:workspaceId/governance-chain", ({ params }) => {
    return HttpResponse.json({ ...governanceChain, workspace_id: String(params.workspaceId) });
  }),
  http.put("*/api/v1/workspaces/:workspaceId/governance-chain", async ({ params, request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    governanceChain.workspace_id = String(params.workspaceId);
    governanceChain.observer_fqns = Array.isArray(body.observer_fqns) ? body.observer_fqns.map(String) : [];
    governanceChain.judge_fqns = Array.isArray(body.judge_fqns) ? body.judge_fqns.map(String) : [];
    governanceChain.enforcer_fqns = Array.isArray(body.enforcer_fqns) ? body.enforcer_fqns.map(String) : [];
    return HttpResponse.json(governanceChain);
  }),
  http.get("*/api/v1/workspaces/:workspaceId/visibility", ({ params }) => {
    return HttpResponse.json({ ...visibilityState, workspace_id: String(params.workspaceId) });
  }),
  http.put("*/api/v1/workspaces/:workspaceId/visibility", async ({ params, request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    visibilityState.workspace_id = String(params.workspaceId);
    visibilityState.visibility_agents = Array.isArray(body.visibility_agents) ? body.visibility_agents.map(String) : [];
    return HttpResponse.json(visibilityState);
  }),
  http.get("*/api/v1/alerts/rules", () => {
    return HttpResponse.json(alertRules);
  }),
  http.put("*/api/v1/alerts/rules", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    alertRules.items = Array.isArray(body.items) ? body.items : alertRules.items;
    return HttpResponse.json(alertRules);
  }),
  http.get("*/me/alert-settings", () => {
    return HttpResponse.json({
      id: "settings-1",
      user_id: "user-1",
      state_transitions: ["execution.failed", "trust.certification_expired", "governance.verdict_issued"],
      delivery_method: "in_app",
      interaction_mutes: [],
    });
  }),
  http.put("*/me/alert-settings", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      id: "settings-1",
      user_id: "user-1",
      state_transitions: Array.isArray(body.state_transitions) ? body.state_transitions : [],
      delivery_method: body.delivery_method ?? "in_app",
      interaction_mutes: Array.isArray(body.interaction_mutes) ? body.interaction_mutes : [],
    });
  }),
  http.get("*/me/alerts", () => {
    return HttpResponse.json({ items: [], total_unread: unreadCount.count });
  }),
  http.get("*/me/alerts/unread-count", () => {
    return HttpResponse.json(unreadCount);
  }),
  http.get("*/api/v1/alerts/unread-count", () => {
    return HttpResponse.json(unreadCount);
  }),
  http.get("*/api/v1/executions/runtime/warm-pool/status", () => {
    return HttpResponse.json({
      keys: [
        {
          agent_type: "small",
          target_size: 5,
          available_count: 4,
          dispatched_count: 0,
          warming_count: 1,
          last_dispatch_at: now,
        },
      ],
    });
  }),
  http.get("*/governance/verdicts", () => {
    return HttpResponse.json({
      items: [
        {
          id: "verdict-1",
          target_agent_fqn: "risk:fraud-monitor",
          verdict_type: "policy_violation",
          judge_agent_fqn: "ops:judge",
          recommended_action: "warn",
          created_at: now,
          rationale: "Policy warning",
        },
      ],
      next_cursor: null,
    });
  }),
  http.get("*/api/v1/dashboard/metrics", () => {
    return HttpResponse.json({ recent_failures: 2, avg_latency_ms: 842 });
  }),
  http.get("*/health", () => {
    return HttpResponse.json({ uptime_seconds: 172800 });
  }),
  http.post("*/api/v1/registry/:workspaceId/agents/:agentId/decommission", () => {
    return HttpResponse.json({ status: "accepted" }, { status: 202 });
  }),
];
