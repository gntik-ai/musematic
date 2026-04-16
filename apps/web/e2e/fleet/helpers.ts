import type { Page } from "@playwright/test";

export const fleetMembers = [
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
] as const;

export const fleetCatalog = [
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
] as const;

function matchSearch(value: string, search: string): boolean {
  const term = search.trim().toLowerCase();
  if (!term) {
    return true;
  }

  return value.toLowerCase().includes(term);
}

function matchCsvFilter(filterValue: string, candidate: string): boolean {
  if (!filterValue) {
    return true;
  }

  return filterValue.split(",").includes(candidate);
}

export async function installFleetState(page: Page) {
  await page.addInitScript(() => {
    class MockWebSocket extends EventTarget {
      static OPEN = 1;
      readyState = 1;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;

      constructor() {
        super();
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

      send() {}
    }

    window.WebSocket = MockWebSocket as unknown as typeof window.WebSocket;

    localStorage.setItem(
      "auth-storage",
      JSON.stringify({
        state: {
          user: {
            id: "user-1",
            email: "operator@musematic.dev",
            displayName: "Operator",
            avatarUrl: null,
            roles: ["workspace_admin", "agent_operator"],
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
            description: "Primary risk workspace",
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

export async function mockFleetApi(page: Page) {
  let fleetStatus: "active" | "degraded" | "paused" | "archived" = "degraded";
  let stressStatus: "running" | "cancelled" = "running";

  await page.route("**/api/v1/fleets?**", async (route) => {
    const url = new URL(route.request().url());
    const search = url.searchParams.get("search") ?? "";
    const status = url.searchParams.get("status") ?? "";
    const topology = url.searchParams.get("topology_type") ?? "";
    const healthMin = Number(url.searchParams.get("health_min") ?? "0");
    const pageValue = Number(url.searchParams.get("page") ?? "1");
    const size = Number(url.searchParams.get("size") ?? "20");

    const filtered = fleetCatalog
      .map((entry) => ({
        ...entry,
        status: entry.id === "fleet-1" ? fleetStatus : entry.status,
      }))
      .filter(
        (entry) =>
          matchSearch(entry.name, search) &&
          matchCsvFilter(status, entry.status) &&
          matchCsvFilter(topology, entry.topology_type) &&
          entry.health_pct >= healthMin,
      );

    const paged = filtered.slice((pageValue - 1) * size, pageValue * size);

    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: paged,
        total: filtered.length,
        page: pageValue,
        size,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...fleetCatalog[0],
        status: fleetStatus,
        members: fleetMembers,
        topology_version: {
          id: "topology-1",
          fleet_id: "fleet-1",
          topology_type: "hybrid",
          version: 3,
          is_current: true,
          created_at: "2026-04-16T10:00:00.000Z",
          config: {
            nodes: fleetMembers.map((member) => ({
              id: member.id,
              agent_fqn: member.agent_fqn,
              role: member.role,
            })),
            edges: [
              { source: "member-1", target: "member-2", type: "delegation" },
              { source: "member-2", target: "member-3", type: "observation" },
            ],
          },
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
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/health", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        fleet_id: "fleet-1",
        status: fleetStatus,
        health_pct: 62,
        quorum_met: true,
        available_count: 2,
        total_count: 3,
        last_updated: "2026-04-16T11:00:00.000Z",
        member_statuses: fleetMembers.map((member) => ({
          agent_fqn: member.agent_fqn,
          health_pct: member.health_pct,
          availability: member.availability,
        })),
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/members", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: fleetMembers }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/topology/history", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "topology-1",
            fleet_id: "fleet-1",
            topology_type: "hybrid",
            version: 3,
            is_current: true,
            created_at: "2026-04-16T10:00:00.000Z",
            config: {
              nodes: fleetMembers.map((member) => ({
                id: member.id,
                agent_fqn: member.agent_fqn,
                role: member.role,
              })),
              edges: [
                { source: "member-1", target: "member-2", type: "delegation" },
                { source: "member-2", target: "member-3", type: "observation" },
              ],
            },
          },
        ],
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/performance-profile/history?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
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
        ],
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/governance-chain", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "gov-1",
        fleet_id: "fleet-1",
        version: 1,
        observer_fqns: ["risk:observer-one"],
        judge_fqns: ["risk:judge-one"],
        enforcer_fqns: ["risk:enforcer-one"],
        policy_binding_ids: ["policy-1"],
        is_current: true,
        is_default: true,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/orchestration-rules", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
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
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/personality-profile", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: "persona-1",
        fleet_id: "fleet-1",
        communication_style: "structured",
        decision_speed: "deliberate",
        risk_tolerance: "moderate",
        autonomy_level: "semi_autonomous",
        version: 1,
        is_current: true,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/observer-findings?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "finding-1",
            fleet_id: "fleet-1",
            observer_fqn: "risk:observer-one",
            observer_name: "Observer One",
            severity: "critical",
            description: "Latency spike detected in fraud escalation workflow.",
            suggested_actions: ["Reduce max parallelism"],
            acknowledged: false,
            acknowledged_by: null,
            acknowledged_at: null,
            created_at: "2026-04-16T11:10:00.000Z",
          },
        ],
        next_cursor: null,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/pause", async (route) => {
    fleetStatus = "paused";
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ status: "pausing", active_executions: 0 }),
      status: 200,
    });
  });

  await page.route("**/api/v1/fleets/fleet-1/resume", async (route) => {
    fleetStatus = "active";
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ status: "active" }),
      status: 200,
    });
  });

  await page.route("**/api/v1/registry/agents?**", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            fqn: "risk:new-worker",
            name: "New Worker",
            namespace: "risk",
            local_name: "new-worker",
            maturity_level: "production",
            status: "active",
            revision_count: 1,
            latest_revision_number: 1,
            updated_at: "2026-04-16T11:00:00.000Z",
            workspace_id: "workspace-1",
          },
        ],
        next_cursor: null,
        total: 1,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/simulation/runs", async (route) => {
    stressStatus = "running";
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        simulation_run_id: "run-1",
        status: "running",
      }),
      status: 201,
    });
  });

  await page.route("**/api/v1/simulation/runs/run-1", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        simulation_run_id: "run-1",
        status: stressStatus,
        elapsed_seconds: 45,
        total_seconds: 900,
        simulated_executions: 32,
        current_success_rate: 0.81,
        current_avg_latency_ms: 1210,
      }),
      status: 200,
    });
  });

  await page.route("**/api/v1/simulation/runs/run-1/cancel", async (route) => {
    stressStatus = "cancelled";
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ status: "cancelled" }),
      status: 200,
    });
  });
}
