import { http, HttpResponse } from "msw";
import type {
  AdminUserRow,
  ConnectorTypeGlobalConfig,
  DefaultQuotas,
  EmailDeliveryConfig,
  SecurityPolicySettings,
  SignupPolicySettings,
  WorkspaceQuotaOverride,
  WorkspaceSearchItem,
} from "@/lib/types/admin";

function nowVersion(): string {
  return new Date().toISOString();
}

function buildUsers(): AdminUserRow[] {
  return [
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
    {
      id: "user-3",
      name: "Morgan Suspended",
      email: "morgan.suspended@musematic.dev",
      status: "suspended",
      role: "workspace_viewer",
      last_login_at: "2026-04-01T09:00:00.000Z",
      created_at: "2026-02-25T15:00:00.000Z",
      available_actions: ["reactivate"],
    },
    {
      id: "user-4",
      name: "Alex Blocked",
      email: "alex.blocked@musematic.dev",
      status: "blocked",
      role: "workspace_member",
      last_login_at: null,
      created_at: "2026-01-18T07:30:00.000Z",
      available_actions: [],
    },
  ];
}

function buildSignupPolicy(): SignupPolicySettings {
  return {
    signup_mode: "open",
    mfa_enforcement: "optional",
    updated_at: nowVersion(),
  };
}

function buildDefaultQuotas(): DefaultQuotas {
  return {
    max_agents: 100,
    max_concurrent_executions: 30,
    max_sandboxes: 12,
    monthly_token_budget: 1000,
    storage_quota_gb: 500,
    updated_at: nowVersion(),
  };
}

function buildWorkspaceOverrides(): Record<string, WorkspaceQuotaOverride> {
  return {
    "workspace-1": {
      workspace_id: "workspace-1",
      workspace_name: "Signal Lab",
      max_agents: 250,
      max_concurrent_executions: null,
      max_sandboxes: 20,
      monthly_token_budget: 5000,
      storage_quota_gb: null,
      updated_at: nowVersion(),
    },
    "workspace-2": {
      workspace_id: "workspace-2",
      workspace_name: "Trust Foundry",
      max_agents: null,
      max_concurrent_executions: 15,
      max_sandboxes: null,
      monthly_token_budget: null,
      storage_quota_gb: 250,
      updated_at: nowVersion(),
    },
  };
}

function buildWorkspaces(): WorkspaceSearchItem[] {
  return [
    { id: "workspace-1", name: "Signal Lab" },
    { id: "workspace-2", name: "Trust Foundry" },
    { id: "workspace-3", name: "Acme Corp" },
    { id: "workspace-4", name: "Northwind Research" },
  ];
}

function buildConnectors(): ConnectorTypeGlobalConfig[] {
  return [
    {
      slug: "slack",
      display_name: "Slack",
      description: "Slack workspace messages and slash commands.",
      is_enabled: true,
      active_instance_count: 4,
      max_payload_size_bytes: 65_536,
      default_retry_count: 3,
      updated_at: nowVersion(),
    },
    {
      slug: "telegram",
      display_name: "Telegram",
      description: "Telegram bot webhooks.",
      is_enabled: true,
      active_instance_count: 1,
      max_payload_size_bytes: 32_768,
      default_retry_count: 2,
      updated_at: nowVersion(),
    },
    {
      slug: "webhook",
      display_name: "Webhook",
      description: "Outbound HTTP callbacks for workflows.",
      is_enabled: true,
      active_instance_count: 8,
      max_payload_size_bytes: 131_072,
      default_retry_count: 5,
      updated_at: nowVersion(),
    },
    {
      slug: "email",
      display_name: "Email",
      description: "Email delivery connectors.",
      is_enabled: true,
      active_instance_count: 3,
      max_payload_size_bytes: 26_214,
      default_retry_count: 2,
      updated_at: nowVersion(),
    },
  ];
}

function buildEmailConfig(): EmailDeliveryConfig {
  return {
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
    last_delivery_at: "2026-04-12T07:10:00.000Z",
    updated_at: nowVersion(),
  };
}

function buildSecurityPolicy(): SecurityPolicySettings {
  return {
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
  };
}

export interface AdminMockState {
  users: AdminUserRow[];
  signupPolicy: SignupPolicySettings;
  defaultQuotas: DefaultQuotas;
  workspaceOverrides: Record<string, WorkspaceQuotaOverride>;
  workspaces: WorkspaceSearchItem[];
  connectors: ConnectorTypeGlobalConfig[];
  emailConfig: EmailDeliveryConfig;
  securityPolicy: SecurityPolicySettings;
}

export function createAdminMockState(): AdminMockState {
  return {
    users: buildUsers(),
    signupPolicy: buildSignupPolicy(),
    defaultQuotas: buildDefaultQuotas(),
    workspaceOverrides: buildWorkspaceOverrides(),
    workspaces: buildWorkspaces(),
    connectors: buildConnectors(),
    emailConfig: buildEmailConfig(),
    securityPolicy: buildSecurityPolicy(),
  };
}

export const adminFixtures = createAdminMockState();

export function resetAdminFixtures(): void {
  const fresh = createAdminMockState();
  adminFixtures.users = fresh.users;
  adminFixtures.signupPolicy = fresh.signupPolicy;
  adminFixtures.defaultQuotas = fresh.defaultQuotas;
  adminFixtures.workspaceOverrides = fresh.workspaceOverrides;
  adminFixtures.workspaces = fresh.workspaces;
  adminFixtures.connectors = fresh.connectors;
  adminFixtures.emailConfig = fresh.emailConfig;
  adminFixtures.securityPolicy = fresh.securityPolicy;
}

function jsonPreconditionFailed(message: string) {
  return HttpResponse.json(
    {
      error: {
        code: "stale_data",
        message,
      },
    },
    { status: 412 },
  );
}

function replaceUserStatus(userId: string, status: AdminUserRow["status"]) {
  adminFixtures.users = adminFixtures.users.map((user) => {
    if (user.id !== userId) {
      return user;
    }

    const available_actions =
      status === "pending_approval"
        ? ["approve", "reject"]
        : status === "active"
          ? ["suspend"]
          : status === "suspended"
            ? ["reactivate"]
            : [];

    return {
      ...user,
      status,
      available_actions,
    };
  });
}

export const adminHandlers = [
  http.get("*/api/v1/admin/users", ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get("search")?.toLowerCase() ?? "";
    const status = url.searchParams.get("status");
    const page = Number(url.searchParams.get("page") ?? "1");
    const pageSize = Number(url.searchParams.get("page_size") ?? "20");

    const filtered = adminFixtures.users.filter((user) => {
      const matchesSearch =
        !search ||
        user.name.toLowerCase().includes(search) ||
        user.email.toLowerCase().includes(search);
      const matchesStatus = !status || user.status === status;
      return matchesSearch && matchesStatus;
    });

    const start = (page - 1) * pageSize;
    const items = filtered.slice(start, start + pageSize);

    return HttpResponse.json({
      items,
      total: filtered.length,
      page,
      page_size: pageSize,
    });
  }),
  http.post("*/api/v1/admin/users/:id/approve", ({ params }) => {
    replaceUserStatus(String(params.id), "active");
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/admin/users/:id/reject", ({ params }) => {
    replaceUserStatus(String(params.id), "blocked");
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/admin/users/:id/suspend", ({ params }) => {
    const userId = String(params.id);
    if (userId === "admin-1") {
      return HttpResponse.json(
        {
          error: {
            code: "cannot_suspend_self",
            message: "You cannot suspend your own account",
          },
        },
        { status: 403 },
      );
    }

    replaceUserStatus(userId, "suspended");
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/admin/users/:id/reactivate", ({ params }) => {
    replaceUserStatus(String(params.id), "active");
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("*/api/v1/admin/settings/signup", () =>
    HttpResponse.json(adminFixtures.signupPolicy),
  ),
  http.patch("*/api/v1/admin/settings/signup", async ({ request }) => {
    const version = request.headers.get("If-Unmodified-Since");
    if (version !== adminFixtures.signupPolicy.updated_at) {
      return jsonPreconditionFailed("Signup policy has changed");
    }

    const body = (await request.json()) as Omit<
      SignupPolicySettings,
      "updated_at"
    >;
    adminFixtures.signupPolicy = {
      ...body,
      updated_at: nowVersion(),
    };
    return HttpResponse.json(adminFixtures.signupPolicy);
  }),
  http.get("*/api/v1/admin/settings/quotas", () =>
    HttpResponse.json(adminFixtures.defaultQuotas),
  ),
  http.patch("*/api/v1/admin/settings/quotas", async ({ request }) => {
    const version = request.headers.get("If-Unmodified-Since");
    if (version !== adminFixtures.defaultQuotas.updated_at) {
      return jsonPreconditionFailed("Default quotas have changed");
    }

    const body = (await request.json()) as Omit<DefaultQuotas, "updated_at">;
    adminFixtures.defaultQuotas = {
      ...body,
      updated_at: nowVersion(),
    };
    return HttpResponse.json(adminFixtures.defaultQuotas);
  }),
  http.get("*/api/v1/admin/settings/quotas/workspaces/:workspaceId", ({ params }) => {
    const workspaceId = String(params.workspaceId);
    const payload =
      adminFixtures.workspaceOverrides[workspaceId] ?? {
        workspace_id: workspaceId,
        workspace_name:
          adminFixtures.workspaces.find((workspace) => workspace.id === workspaceId)
            ?.name ?? "Unknown workspace",
        max_agents: null,
        max_concurrent_executions: null,
        max_sandboxes: null,
        monthly_token_budget: null,
        storage_quota_gb: null,
        updated_at: nowVersion(),
      };

    adminFixtures.workspaceOverrides[workspaceId] = payload;
    return HttpResponse.json(payload);
  }),
  http.patch(
    "*/api/v1/admin/settings/quotas/workspaces/:workspaceId",
    async ({ params, request }) => {
      const workspaceId = String(params.workspaceId);
      const current = adminFixtures.workspaceOverrides[workspaceId];
      const version = request.headers.get("If-Unmodified-Since");

      if (current && version !== current.updated_at) {
        return jsonPreconditionFailed("Workspace quotas have changed");
      }

      const body = (await request.json()) as Omit<
        WorkspaceQuotaOverride,
        "updated_at" | "workspace_id" | "workspace_name"
      >;
      const workspaceName =
        adminFixtures.workspaces.find((workspace) => workspace.id === workspaceId)
          ?.name ?? "Unknown workspace";

      adminFixtures.workspaceOverrides[workspaceId] = {
        workspace_id: workspaceId,
        workspace_name: workspaceName,
        ...body,
        updated_at: nowVersion(),
      };

      return HttpResponse.json(adminFixtures.workspaceOverrides[workspaceId]);
    },
  ),
  http.get("*/api/v1/admin/workspaces", ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get("search")?.toLowerCase() ?? "";
    const items = adminFixtures.workspaces.filter((workspace) =>
      workspace.name.toLowerCase().includes(search),
    );
    return HttpResponse.json({
      items,
      total: items.length,
    });
  }),
  http.get("*/api/v1/admin/settings/connectors", () =>
    HttpResponse.json(adminFixtures.connectors),
  ),
  http.patch(
    "*/api/v1/admin/settings/connectors/:typeSlug",
    async ({ params, request }) => {
      const typeSlug = String(params.typeSlug);
      const body = (await request.json()) as { is_enabled: boolean };

      adminFixtures.connectors = adminFixtures.connectors.map((connector) =>
        connector.slug === typeSlug
          ? {
              ...connector,
              is_enabled: body.is_enabled,
              updated_at: nowVersion(),
            }
          : connector,
      );

      return HttpResponse.json(
        adminFixtures.connectors.find((connector) => connector.slug === typeSlug),
      );
    },
  ),
  http.get("*/api/v1/admin/settings/email", () =>
    HttpResponse.json(adminFixtures.emailConfig),
  ),
  http.patch("*/api/v1/admin/settings/email", async ({ request }) => {
    const version = request.headers.get("If-Unmodified-Since");
    if (version !== adminFixtures.emailConfig.updated_at) {
      return jsonPreconditionFailed("Email settings have changed");
    }

    const body = (await request.json()) as Record<string, unknown>;
    if (body.mode === "ses") {
      adminFixtures.emailConfig = {
        mode: "ses",
        ses: {
          region: String(body.region),
          access_key_id: String(body.access_key_id),
          secret_access_key_set:
            body.new_secret_access_key !== undefined
              ? String(body.new_secret_access_key).length > 0
              : adminFixtures.emailConfig.mode === "ses"
                ? adminFixtures.emailConfig.ses?.secret_access_key_set ?? false
                : false,
        },
        from_address: String(body.from_address),
        from_name: String(body.from_name),
        verification_status: adminFixtures.emailConfig.verification_status,
        last_delivery_at: adminFixtures.emailConfig.last_delivery_at,
        updated_at: nowVersion(),
      };
    } else {
      adminFixtures.emailConfig = {
        mode: "smtp",
        smtp: {
          host: String(body.host),
          port: Number(body.port),
          username: String(body.username),
          password_set:
            body.new_password !== undefined
              ? String(body.new_password).length > 0
              : adminFixtures.emailConfig.mode === "smtp"
                ? adminFixtures.emailConfig.smtp?.password_set ?? false
                : false,
          encryption: body.encryption as "tls" | "starttls" | "none",
        },
        from_address: String(body.from_address),
        from_name: String(body.from_name),
        verification_status: adminFixtures.emailConfig.verification_status,
        last_delivery_at: adminFixtures.emailConfig.last_delivery_at,
        updated_at: nowVersion(),
      };
    }

    return HttpResponse.json(adminFixtures.emailConfig);
  }),
  http.post("*/api/v1/admin/settings/email/test", async ({ request }) => {
    const body = (await request.json()) as { recipient?: string };
    if (body.recipient?.includes("fail")) {
      return HttpResponse.json(
        {
          success: false,
          message: "SMTP connection refused",
        },
        { status: 400 },
      );
    }

    return HttpResponse.json({
      success: true,
      message: "Test email sent successfully",
    });
  }),
  http.get("*/api/v1/admin/settings/security", () =>
    HttpResponse.json(adminFixtures.securityPolicy),
  ),
  http.patch("*/api/v1/admin/settings/security", async ({ request }) => {
    const version = request.headers.get("If-Unmodified-Since");
    if (version !== adminFixtures.securityPolicy.updated_at) {
      return jsonPreconditionFailed("Security settings have changed");
    }

    const body = (await request.json()) as Omit<
      SecurityPolicySettings,
      "updated_at"
    >;
    adminFixtures.securityPolicy = {
      ...body,
      updated_at: nowVersion(),
    };
    return HttpResponse.json(adminFixtures.securityPolicy);
  }),
];
