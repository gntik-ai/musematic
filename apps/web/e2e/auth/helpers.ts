import type { Page, Route } from "@playwright/test";

interface MockAuthOptions {
  loginMode?: "success" | "mfa" | "invalid" | "locked";
  mfaEnrolled?: boolean;
}

function buildWorkspaceSummary(workspaceId: string) {
  return {
    workspace_id: workspaceId,
    active_agents: 12,
    active_agents_change: 3,
    running_executions: 4,
    running_executions_change: 0,
    pending_approvals: 2,
    pending_approvals_change: -1,
    cost_current: 142_50,
    cost_previous: 130_20,
    period_label: "Apr 2026",
  };
}

function buildRecentActivity(workspaceId: string) {
  return {
    workspace_id: workspaceId,
    items: [
      {
        id: "execution-1",
        type: "execution",
        title: "Execution completed: daily-report-generator",
        status: "completed",
        timestamp: "2026-04-11T09:58:00.000Z",
        href: "/executions/execution-1",
        metadata: {
          workflow_name: "Daily report generator",
        },
      },
      {
        id: "interaction-1",
        type: "interaction",
        title: "Interaction started: workspace-q-and-a",
        status: "running",
        timestamp: "2026-04-11T09:54:00.000Z",
        href: "/interactions/interaction-1",
        metadata: {
          agent_fqn: "musematic.workspace_qna",
        },
      },
    ],
  };
}

function buildPendingActions(workspaceId: string) {
  return {
    workspace_id: workspaceId,
    total: 1,
    items: [
      {
        id: "approval-1",
        type: "approval",
        title: "Approval required: policy-enforcement-agent",
        description: "Approve the run before it reaches external systems.",
        urgency: "medium",
        created_at: "2026-04-11T09:52:00.000Z",
        href: "/approvals/approval-1",
        actions: [
          {
            id: "approve",
            label: "Approve",
            variant: "default",
            action: "approve",
            endpoint: `/api/v1/workspaces/${workspaceId}/approvals/approval-1/approve`,
            method: "POST",
          },
        ],
      },
    ],
  };
}

function buildUser(mfaEnrolled: boolean) {
  return {
    id: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001",
    email: "alex@musematic.dev",
    display_name: "Alex Mercer",
    avatar_url: null,
    roles: ["workspace_admin", "agent_operator", "analytics_viewer"],
    workspace_id: "workspace-1",
    mfa_enrolled: mfaEnrolled,
  };
}

function buildAuthSuccess(mfaEnrolled: boolean) {
  return {
    access_token: "mock-access-token",
    refresh_token: "mock-refresh-token",
    expires_in: 900,
    user: buildUser(mfaEnrolled),
  };
}

async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(json),
  });
}

export async function mockAuthApi(page: Page, options: MockAuthOptions = {}) {
  const { loginMode = "success", mfaEnrolled = true } = options;

  await page.route("**/api/v1/auth/login", async (route) => {
    if (loginMode === "invalid") {
      await fulfillJson(
        route,
        {
          error: {
            code: "INVALID_CREDENTIALS",
            message: "Invalid email or password",
          },
        },
        401,
      );
      return;
    }

    if (loginMode === "locked") {
      await fulfillJson(
        route,
        {
          error: {
            code: "ACCOUNT_LOCKED",
            message: "Account locked",
            lockout_seconds: 60,
          },
        },
        429,
      );
      return;
    }

    if (loginMode === "mfa") {
      await fulfillJson(route, {
        mfa_required: true,
        session_token: "mfa-session-token",
      });
      return;
    }

    await fulfillJson(route, buildAuthSuccess(mfaEnrolled));
  });

  await page.route("**/api/v1/auth/mfa/verify", async (route) => {
    await fulfillJson(route, {
      ...buildAuthSuccess(true),
      recovery_code_consumed: false,
    });
  });

  await page.route("**/api/v1/auth/mfa/enroll", async (route) => {
    await fulfillJson(route, {
      provisioning_uri:
        "otpauth://totp/Musematic:alex%40musematic.dev?secret=JBSWY3DPEHPK3PXP&issuer=Musematic",
      secret_key: "JBSW Y3DP EHPK 3PXP",
    });
  });

  await page.route("**/api/v1/auth/mfa/confirm", async (route) => {
    await fulfillJson(route, {
      recovery_codes: [
        "alpha-bravo-charlie",
        "delta-echo-foxtrot",
        "golf-hotel-india",
        "juliet-kilo-lima",
      ],
    });
  });

  await page.route("**/api/v1/password-reset/request", async (route) => {
    await fulfillJson(route, {}, 202);
  });

  await page.route("**/api/v1/password-reset/complete", async (route) => {
    await fulfillJson(route, { success: true });
  });

  await page.route("**/api/v1/workspaces/*/analytics/summary", async (route) => {
    await fulfillJson(route, buildWorkspaceSummary("workspace-1"));
  });

  await page.route(
    "**/api/v1/workspaces/*/dashboard/recent-activity",
    async (route) => {
      await fulfillJson(route, buildRecentActivity("workspace-1"));
    },
  );

  await page.route(
    "**/api/v1/workspaces/*/dashboard/pending-actions",
    async (route) => {
      await fulfillJson(route, buildPendingActions("workspace-1"));
    },
  );
}

export async function signIn(
  page: Page,
  options: { email?: string; password?: string } = {},
) {
  const { email = "alex@musematic.dev", password = "SecretPass1!" } = options;

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
}
