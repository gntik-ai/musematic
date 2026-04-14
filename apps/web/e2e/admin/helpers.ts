import type { Page, Route } from "@playwright/test";

interface AdminUserRecord {
  id: string;
  name: string;
  email: string;
  status: "pending_approval" | "active" | "suspended" | "blocked";
  role: string;
  last_login_at: string | null;
  created_at: string;
  available_actions: Array<"approve" | "reject" | "suspend" | "reactivate">;
}

function nowVersion(): string {
  return new Date().toISOString();
}

function createAdminState(): {
  connectorTypes: Array<{
    slug: string;
    display_name: string;
    description: string;
    is_enabled: boolean;
    active_instance_count: number;
    max_payload_size_bytes: number;
    default_retry_count: number;
    updated_at: string;
  }>;
  defaultQuotas: {
    max_agents: number;
    max_concurrent_executions: number;
    max_sandboxes: number;
    monthly_token_budget: number;
    storage_quota_gb: number;
    updated_at: string;
  };
  emailConfig: {
    mode: "smtp" | "ses";
    smtp?: {
      host: string;
      port: number;
      username: string;
      password_set: boolean;
      encryption: "tls" | "starttls" | "none";
    };
    ses?: {
      region: string;
      access_key_id: string;
      secret_access_key_set: boolean;
    };
    from_address: string;
    from_name: string;
    verification_status: "verified" | "unverified" | "error";
    last_delivery_at: string | null;
    updated_at: string;
  };
  securityPolicy: {
    password_min_length: number;
    password_require_uppercase: boolean;
    password_require_lowercase: boolean;
    password_require_digit: boolean;
    password_require_special: boolean;
    password_expiry_days: null;
    session_duration_minutes: number;
    lockout_max_attempts: number;
    lockout_duration_minutes: number;
    updated_at: string;
  };
  signupPolicy: {
    signup_mode: "open" | "invite_only" | "admin_approval";
    mfa_enforcement: "optional" | "required";
    updated_at: string;
  };
  users: AdminUserRecord[];
  workspaceOverride: {
    workspace_id: string;
    workspace_name: string;
    max_agents: number | null;
    max_concurrent_executions: number | null;
    max_sandboxes: number | null;
    monthly_token_budget: number | null;
    storage_quota_gb: number | null;
    updated_at: string;
  };
  workspaces: Array<{ id: string; name: string }>;
} {
  const users: AdminUserRecord[] = [
    {
      id: "admin-1",
      name: "Pat Admin",
      email: "pat.admin@musematic.dev",
      status: "active",
      role: "platform_admin",
      last_login_at: "2026-04-12T08:45:00.000Z",
      created_at: "2026-03-01T12:00:00.000Z",
      available_actions: ["suspend"],
    },
    {
      id: "user-1",
      name: "John Example",
      email: "john@example.com",
      status: "pending_approval",
      role: "workspace_owner",
      last_login_at: null,
      created_at: "2026-04-09T08:10:00.000Z",
      available_actions: ["approve", "reject"],
    },
    {
      id: "user-2",
      name: "Riley Ops",
      email: "riley.ops@musematic.dev",
      status: "active",
      role: "workspace_admin",
      last_login_at: "2026-04-11T16:20:00.000Z",
      created_at: "2026-03-14T10:20:00.000Z",
      available_actions: ["suspend"],
    },
  ];

  return {
    connectorTypes: [
      {
        slug: "slack",
        display_name: "Slack",
        description: "Route workspace notifications into Slack channels.",
        is_enabled: true,
        active_instance_count: 3,
        max_payload_size_bytes: 262144,
        default_retry_count: 3,
        updated_at: nowVersion(),
      },
      {
        slug: "email",
        display_name: "Email",
        description: "Deliver outbound messages through SMTP or SES.",
        is_enabled: true,
        active_instance_count: 1,
        max_payload_size_bytes: 1048576,
        default_retry_count: 5,
        updated_at: nowVersion(),
      },
    ],
    defaultQuotas: {
      max_agents: 100,
      max_concurrent_executions: 30,
      max_sandboxes: 12,
      monthly_token_budget: 1000,
      storage_quota_gb: 500,
      updated_at: nowVersion(),
    },
    emailConfig: {
      mode: "smtp",
      smtp: {
        host: "smtp.musematic.dev",
        port: 587,
        username: "mailer",
        password_set: true,
        encryption: "starttls",
      },
      from_address: "noreply@musematic.dev",
      from_name: "Musematic",
      verification_status: "verified",
      last_delivery_at: "2026-04-12T12:00:00.000Z",
      updated_at: nowVersion(),
    },
    signupPolicy: {
      signup_mode: "open",
      mfa_enforcement: "optional",
      updated_at: nowVersion(),
    },
    securityPolicy: {
      password_min_length: 12,
      password_require_uppercase: true,
      password_require_lowercase: true,
      password_require_digit: true,
      password_require_special: true,
      password_expiry_days: null,
      session_duration_minutes: 480,
      lockout_max_attempts: 5,
      lockout_duration_minutes: 15,
      updated_at: nowVersion(),
    },
    users,
    workspaceOverride: {
      workspace_id: "workspace-1",
      workspace_name: "Current workspace",
      max_agents: 40,
      max_concurrent_executions: 10,
      max_sandboxes: 4,
      monthly_token_budget: 250,
      storage_quota_gb: 120,
      updated_at: nowVersion(),
    },
    workspaces: [
      { id: "workspace-1", name: "Current workspace" },
      { id: "workspace-2", name: "Operations lab" },
    ],
  };
}

async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(json),
  });
}

function updateUserStatus(
  users: AdminUserRecord[],
  userId: string,
  status: AdminUserRecord["status"],
): AdminUserRecord[] {
  return users.map((user) => {
    if (user.id !== userId) {
      return user;
    }

    const available_actions: AdminUserRecord["available_actions"] =
      status === "pending_approval"
        ? ["approve", "reject"]
        : status === "active"
          ? ["suspend"]
          : status === "suspended"
            ? ["reactivate"]
            : [];

    return {
      ...user,
      available_actions,
      status,
    };
  });
}

export async function mockAdminApi(page: Page) {
  const state = createAdminState();

  await page.route("**/api/v1/admin/users**", async (route) => {
    await fulfillJson(route, {
      items: state.users,
      total: state.users.length,
      page: 1,
      page_size: 20,
    });
  });

  await page.route("**/api/v1/admin/users/*/approve", async (route) => {
    const userId = route.request().url().split("/").slice(-2)[0] ?? "";
    state.users = updateUserStatus(state.users, userId, "active");
    await route.fulfill({ status: 204 });
  });

  await page.route("**/api/v1/admin/users/*/reject", async (route) => {
    const userId = route.request().url().split("/").slice(-2)[0] ?? "";
    state.users = updateUserStatus(state.users, userId, "blocked");
    await route.fulfill({ status: 204 });
  });

  await page.route("**/api/v1/admin/users/*/suspend", async (route) => {
    const userId = route.request().url().split("/").slice(-2)[0] ?? "";
    if (userId === "admin-1") {
      await fulfillJson(
        route,
        {
          error: {
            code: "cannot_suspend_self",
            message: "You cannot suspend your own account",
          },
        },
        403,
      );
      return;
    }

    state.users = updateUserStatus(state.users, userId, "suspended");
    await route.fulfill({ status: 204 });
  });

  await page.route("**/api/v1/admin/users/*/reactivate", async (route) => {
    const userId = route.request().url().split("/").slice(-2)[0] ?? "";
    state.users = updateUserStatus(state.users, userId, "active");
    await route.fulfill({ status: 204 });
  });

  await page.route("**/api/v1/admin/settings/signup", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = (await route.request().postDataJSON()) as {
        signup_mode: "open" | "invite_only" | "admin_approval";
        mfa_enforcement: "optional" | "required";
      };
      state.signupPolicy = {
        ...body,
        updated_at: nowVersion(),
      };
      await fulfillJson(route, state.signupPolicy);
      return;
    }

    await fulfillJson(route, state.signupPolicy);
  });

  await page.route("**/api/v1/admin/settings/security", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = (await route.request().postDataJSON()) as typeof state.securityPolicy;
      state.securityPolicy = {
        ...body,
        updated_at: nowVersion(),
      };
      await fulfillJson(route, state.securityPolicy);
      return;
    }

    await fulfillJson(route, state.securityPolicy);
  });

  await page.route("**/api/v1/admin/settings/quotas", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = (await route.request().postDataJSON()) as Omit<
        typeof state.defaultQuotas,
        "updated_at"
      >;
      state.defaultQuotas = {
        ...body,
        updated_at: nowVersion(),
      };
      await fulfillJson(route, state.defaultQuotas);
      return;
    }

    await fulfillJson(route, state.defaultQuotas);
  });

  await page.route("**/api/v1/admin/workspaces**", async (route) => {
    await fulfillJson(route, {
      items: state.workspaces,
      total: state.workspaces.length,
    });
  });

  await page.route("**/api/v1/admin/settings/quotas/workspaces/*", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = (await route.request().postDataJSON()) as Omit<
        typeof state.workspaceOverride,
        "updated_at" | "workspace_id" | "workspace_name"
      >;
      state.workspaceOverride = {
        ...state.workspaceOverride,
        ...body,
        updated_at: nowVersion(),
      };
      await fulfillJson(route, state.workspaceOverride);
      return;
    }

    await fulfillJson(route, state.workspaceOverride);
  });

  await page.route("**/api/v1/admin/settings/connectors", async (route) => {
    await fulfillJson(route, state.connectorTypes);
  });

  await page.route("**/api/v1/admin/settings/connectors/*", async (route) => {
    const slug = route.request().url().split("/").pop() ?? "";
    const body = (await route.request().postDataJSON().catch(() => null)) as
      | { is_enabled?: boolean }
      | null;

    state.connectorTypes = state.connectorTypes.map((config) =>
      config.slug === slug
        ? {
            ...config,
            is_enabled: body?.is_enabled ?? config.is_enabled,
            updated_at: nowVersion(),
          }
        : config,
    );

    await fulfillJson(
      route,
      state.connectorTypes.find((config) => config.slug === slug) ?? null,
    );
  });

  await page.route("**/api/v1/admin/settings/email", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = (await route.request().postDataJSON()) as Record<string, unknown>;
      state.emailConfig = {
        ...state.emailConfig,
        ...body,
        updated_at: nowVersion(),
      };
      await fulfillJson(route, state.emailConfig);
      return;
    }

    await fulfillJson(route, state.emailConfig);
  });

  await page.route("**/api/v1/admin/settings/email/test", async (route) => {
    await fulfillJson(route, {
      success: true,
      message: "Test email delivered successfully.",
    });
  });
}
