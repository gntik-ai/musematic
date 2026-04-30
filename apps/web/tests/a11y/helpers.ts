import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { auditedSurfaces, surfacesForGroup, type A11ySurfaceGroup } from "@/tests/a11y/audited-surfaces";

const localePattern = /-(en|es|fr|de|ja|zh-CN)$/;
const themePattern = /^a11y-(light|dark|system|high_contrast)-/;

function contextFromProject(projectName: string) {
  return {
    theme: projectName.match(themePattern)?.[1] ?? "system",
    locale: projectName.match(localePattern)?.[1] ?? "en",
  };
}

async function fulfillJson(page: Page, pattern: string, payload: unknown, status = 200) {
  await page.route(pattern, async (route) => {
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}

async function installA11yState(page: Page, theme: string, locale: string) {
  await page.addInitScript(
    ({ theme, locale }) => {
      window.localStorage.setItem(
        "auth-storage",
        JSON.stringify({
          state: {
            user: {
              id: "user-a11y",
              email: "a11y@musematic.dev",
              displayName: "A11y User",
              avatarUrl: null,
              roles: ["superadmin", "platform_admin", "workspace_admin", "agent_operator", "analytics_viewer"],
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
      window.localStorage.setItem("musematic-theme", theme);
      document.cookie = `musematic-theme=${theme}; Path=/; SameSite=Lax`;
      document.cookie = `musematic-locale=${locale}; Path=/; SameSite=Lax`;
    },
    { theme, locale },
  );
}

async function mockA11yApis(page: Page) {
  const creatorProfileId = "22222222-2222-4222-8222-222222222222";
  const creatorContractId = "33333333-3333-4333-8333-333333333333";
  const creatorTemplateId = "44444444-4444-4444-8444-444444444444";
  const oauthProviders = [
    {
      id: "google-provider-id",
      provider_type: "google",
      display_name: "Google",
      enabled: true,
      client_id: "google-client.apps.googleusercontent.com",
      client_secret_ref: "secret/data/musematic/dev/oauth/google/client-secret",
      redirect_uri: "https://app.musematic.dev/auth/oauth/google/callback",
      scopes: ["openid", "email", "profile"],
      domain_restrictions: ["musematic.dev"],
      org_restrictions: [],
      group_role_mapping: { "admins@musematic.dev": "admin" },
      default_role: "member",
      require_mfa: false,
      source: "env_var",
      last_edited_by: null,
      last_edited_at: null,
      last_successful_auth_at: "2026-04-18T07:30:00.000Z",
      created_at: "2026-04-18T07:00:00.000Z",
      updated_at: "2026-04-18T07:30:00.000Z",
    },
    {
      id: "github-provider-id",
      provider_type: "github",
      display_name: "GitHub",
      enabled: true,
      client_id: "github-client",
      client_secret_ref: "secret/data/musematic/dev/oauth/github/client-secret",
      redirect_uri: "https://app.musematic.dev/auth/oauth/github/callback",
      scopes: ["read:user", "user:email"],
      domain_restrictions: [],
      org_restrictions: ["musematic"],
      group_role_mapping: { "musematic/platform-admins": "admin" },
      default_role: "member",
      require_mfa: false,
      source: "manual",
      last_edited_by: "admin-user-id",
      last_edited_at: "2026-04-18T07:45:00.000Z",
      last_successful_auth_at: null,
      created_at: "2026-04-18T07:00:00.000Z",
      updated_at: "2026-04-18T07:45:00.000Z",
    },
  ];
  const oauthRateLimits = {
    per_ip_max: 10,
    per_ip_window: 60,
    per_user_max: 10,
    per_user_window: 60,
    global_max: 100,
    global_window: 60,
  };
  const timestamp = "2026-04-30T09:00:00.000Z";
  const alert = {
    id: "00000000-0000-0000-0000-000000000101",
    alert_type: "security.session",
    title: "New security alert",
    body: "A new session was created from Madrid.",
    urgency: "high",
    read: false,
    interaction_id: null,
    source_reference: { channel: "in_app", url: "/settings/security/activity" },
    created_at: timestamp,
    updated_at: timestamp,
  };
  const notificationPreferences = {
    state_transitions: ["working_to_pending", "any_to_complete", "any_to_failed"],
    delivery_method: "in_app",
    webhook_url: null,
    per_channel_preferences: {
      "security.session": ["in_app", "email"],
      "incidents.created": ["in_app", "email", "slack"],
      "privacy.dsr": ["in_app"],
    },
    digest_mode: {
      in_app: "immediate",
      email: "daily",
      webhook: "immediate",
      slack: "hourly",
      teams: "hourly",
      sms: "immediate",
    },
    quiet_hours: {
      start_time: "22:00",
      end_time: "07:00",
      timezone: "Europe/Madrid",
    },
  };
  const serviceAccount = {
    service_account_id: "00000000-0000-0000-0000-000000000201",
    name: "Local automation",
    role: "service_account",
    status: "active",
    workspace_id: null,
    created_at: timestamp,
    last_used_at: null,
    api_key_prefix: "hash:fixture201",
  };
  const consent = {
    id: "00000000-0000-0000-0000-000000000301",
    consent_type: "ai_interaction",
    granted: true,
    granted_at: timestamp,
    revoked_at: null,
    workspace_id: null,
  };
  const dsr = {
    id: "00000000-0000-0000-0000-000000000401",
    subject_user_id: "00000000-0000-0000-0000-000000000501",
    request_type: "access",
    requested_by: "00000000-0000-0000-0000-000000000501",
    status: "received",
    legal_basis: "self_service",
    scheduled_release_at: null,
    requested_at: timestamp,
    completed_at: null,
    completion_proof_hash: null,
    failure_reason: null,
    tombstone_id: null,
  };
  const workspaceId = "workspace-1";
  const connectorId = "connector-1";
  const iborConnectorId = "ibor-connector-1";
  const workspaceSettings = {
    workspace_id: workspaceId,
    subscribed_agents: [],
    subscribed_fleets: [],
    subscribed_policies: [],
    subscribed_connectors: [],
    cost_budget: { amount: 10000, hard_cap_enabled: true },
    quota_config: { agents: 20, fleets: 4, executions: 10, storage_gb: 250 },
    dlp_rules: { enabled: true, pii: "block" },
    residency_config: { region: "eu-west-1", tier: "regulated" },
    updated_at: timestamp,
  };
  const connector = {
    id: connectorId,
    workspace_id: workspaceId,
    connector_type_id: "slack-type",
    connector_type_slug: "slack",
    name: "Slack workspace alerts",
    config: { channel: "#alerts" },
    status: "active",
    health_status: "healthy",
    last_health_check_at: timestamp,
    health_check_error: null,
    messages_sent: 24,
    messages_failed: 1,
    messages_retried: 1,
    messages_dead_lettered: 0,
    credential_keys: ["bot_token"],
    created_at: timestamp,
    updated_at: timestamp,
  };
  const iborConnector = {
    id: iborConnectorId,
    name: "Corporate directory",
    source_type: "ldap",
    sync_mode: "pull",
    cadence_seconds: 3600,
    credential_ref: "secret/data/musematic/dev/ibor/corporate-directory",
    role_mapping_policy: [],
    enabled: true,
    last_run_at: timestamp,
    last_run_status: "succeeded",
    created_by: "user-a11y",
    created_at: timestamp,
    updated_at: timestamp,
  };

  await fulfillJson(page, "**/api/v1/workspaces", {
    items: [
      {
        id: workspaceId,
        name: "Risk Ops",
        slug: "risk-ops",
        description: "Primary workspace",
        memberCount: 8,
        createdAt: "2026-04-10T09:00:00.000Z",
      },
    ],
  });
  await fulfillJson(page, `**/api/v1/workspaces/${workspaceId}/summary`, {
    workspace_id: workspaceId,
    active_goals: 3,
    executions_in_flight: 5,
    agent_count: 12,
    budget: { amount: 10000, spent: 6000, currency: "USD" },
    quotas: {
      agents: { used: 12, limit: 20 },
      fleets: { used: 2, limit: 4 },
      executions: { used: 5, limit: 10 },
      storage_gb: { used: 80, limit: 250 },
    },
    tags: { domain: ["science", "regulated"] },
    dlp_violations: 2,
    recent_activity: [{ event_type: "auth.workspace.member_added", created_at: timestamp }],
    cards: {},
    cached_until: timestamp,
  });
  await fulfillJson(page, `**/api/v1/workspaces/${workspaceId}/settings`, workspaceSettings);
  await fulfillJson(page, `**/api/v1/workspaces/${workspaceId}/members**`, {
    items: [
      {
        id: "member-owner",
        workspace_id: workspaceId,
        user_id: "user-a11y",
        role: "owner",
        created_at: timestamp,
      },
      {
        id: "member-admin",
        workspace_id: workspaceId,
        user_id: "user-admin",
        role: "admin",
        created_at: timestamp,
      },
    ],
    total: 2,
    page: 1,
    page_size: 50,
    has_next: false,
    has_prev: false,
  });
  await fulfillJson(page, `**/api/v1/workspaces/${workspaceId}/connectors`, {
    items: [connector],
    total: 1,
  });
  await fulfillJson(page, `**/api/v1/workspaces/${workspaceId}/connectors/${connectorId}`, connector);
  await fulfillJson(page, `**/api/v1/workspaces/${workspaceId}/deliveries**`, {
    items: [
      {
        id: "delivery-1",
        workspace_id: workspaceId,
        connector_instance_id: connectorId,
        destination: "#alerts",
        status: "delivered",
        attempt_count: 1,
        max_attempts: 3,
        delivered_at: timestamp,
        error_history: [],
        created_at: timestamp,
        updated_at: timestamp,
      },
      {
        id: "delivery-2",
        workspace_id: workspaceId,
        connector_instance_id: connectorId,
        destination: "#alerts",
        status: "failed",
        attempt_count: 3,
        max_attempts: 3,
        delivered_at: null,
        error_history: [{ error: "rate_limited" }],
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
    total: 2,
  });
  await fulfillJson(page, `**/api/v1/workspaces/${workspaceId}/visibility`, {
    workspace_id: workspaceId,
    visibility_agents: ["science:*"],
    visibility_tools: ["tool://lab/*"],
    updated_at: timestamp,
  });
  await fulfillJson(page, `**/api/v1/tags/workspace/${workspaceId}`, {
    entity_type: "workspace",
    entity_id: workspaceId,
    tags: [{ tag: "science", created_by: null, created_at: timestamp }],
  });
  await fulfillJson(page, `**/api/v1/labels/workspace/${workspaceId}`, {
    entity_type: "workspace",
    entity_id: workspaceId,
    labels: [
      {
        key: "region",
        value: "eu",
        created_by: null,
        created_at: timestamp,
        updated_at: timestamp,
        is_reserved: false,
      },
    ],
  });
  await fulfillJson(page, "**/api/v1/admin/workspaces**", {
    items: [{ id: workspaceId, name: "Risk Ops" }],
    total: 1,
  });
  await fulfillJson(page, "**/api/v1/admin/settings/connectors", [
    {
      slug: "slack",
      display_name: "Slack",
      description: "Workspace messaging connector.",
      is_enabled: true,
      active_instance_count: 1,
      max_payload_size_bytes: 262144,
      default_retry_count: 3,
      updated_at: timestamp,
    },
  ]);
  await fulfillJson(page, "**/api/v1/auth/ibor/connectors", {
    items: [iborConnector],
  });
  await fulfillJson(page, `**/api/v1/auth/ibor/connectors/${iborConnectorId}/sync-history**`, {
    items: [
      {
        id: "sync-1",
        connector_id: iborConnectorId,
        mode: "pull",
        started_at: timestamp,
        finished_at: timestamp,
        status: "succeeded",
        counts: { users: 12 },
        error_details: [],
        triggered_by: null,
      },
    ],
    next_cursor: null,
  });
  await fulfillJson(page, "**/api/v1/me/preferences", {
    id: "prefs-1",
    user_id: "user-a11y",
    default_workspace_id: "workspace-1",
    theme: "system",
    language: "en",
    timezone: "UTC",
    notification_preferences: {},
    data_export_format: "json",
    is_persisted: true,
    created_at: "2026-04-10T09:00:00.000Z",
    updated_at: "2026-04-10T09:00:00.000Z",
  });
  await fulfillJson(page, "**/me/alerts**", { items: [], total_unread: 0 });
  await fulfillJson(page, "**/api/v1/locales", { items: [] });
  await fulfillJson(page, "**/api/v1/locales/*", {
    locale_code: "en",
    version: 1,
    translations: {},
    published_at: "2026-04-10T09:00:00.000Z",
  });
  await fulfillJson(page, "**/api/v1/me/alerts**", {
    items: [alert],
    next_cursor: null,
    total_unread: 1,
  });
  await fulfillJson(page, "**/api/v1/me/notification-preferences", notificationPreferences);
  await fulfillJson(page, "**/api/v1/me/service-accounts", {
    items: [serviceAccount],
    max_active: 10,
  });
  await fulfillJson(page, "**/api/v1/me/sessions", {
    items: [
      {
        session_id: "00000000-0000-0000-0000-000000000601",
        device_info: "Firefox on Linux",
        ip_address: "203.0.113.10",
        location: "Madrid, Spain",
        created_at: "2026-04-30T07:00:00.000Z",
        last_activity: timestamp,
        is_current: true,
      },
      {
        session_id: "00000000-0000-0000-0000-000000000602",
        device_info: "Chrome on macOS",
        ip_address: "198.51.100.8",
        location: "Lisbon, Portugal",
        created_at: "2026-04-29T15:00:00.000Z",
        last_activity: "2026-04-29T16:00:00.000Z",
        is_current: false,
      },
    ],
  });
  await fulfillJson(page, "**/api/v1/me/activity**", {
    items: [
      {
        id: "00000000-0000-0000-0000-000000000701",
        event_type: "auth.session.revoked",
        audit_event_source: "self_service",
        severity: "info",
        created_at: timestamp,
        canonical_payload: { actor_id: "00000000-0000-0000-0000-000000000501" },
      },
    ],
    next_cursor: null,
  });
  await fulfillJson(page, "**/api/v1/me/consent/history", { items: [consent] });
  await fulfillJson(page, "**/api/v1/me/consent", { items: [consent] });
  await fulfillJson(page, "**/api/v1/me/dsr**", { items: [dsr], next_cursor: null });
  await fulfillJson(page, "**/api/v1/admin/oauth/providers", {
    providers: oauthProviders,
  });
  await fulfillJson(page, "**/api/v1/admin/oauth-providers/*/status", {
    provider_type: "google",
    source: "env_var",
    last_successful_auth_at: "2026-04-18T07:30:00.000Z",
    auth_count_24h: 3,
    auth_count_7d: 11,
    auth_count_30d: 27,
    active_linked_users: 1,
  });
  await fulfillJson(page, "**/api/v1/admin/oauth-providers/*/history", {
    entries: [
      {
        timestamp: "2026-04-18T07:15:00.000Z",
        admin_id: null,
        action: "provider_bootstrapped",
        before: null,
        after: { enabled: true, source: "env_var" },
      },
    ],
    next_cursor: null,
  });
  await fulfillJson(page, "**/api/v1/admin/oauth-providers/*/rate-limits", oauthRateLimits);
  await fulfillJson(page, "**/api/v1/context-engineering/profiles/schema", {
    type: "object",
    properties: {
      name: { type: "string" },
      source_config: { type: "array" },
    },
  });
  await fulfillJson(page, "**/api/v1/context-engineering/profiles/*/versions**", {
    versions: [
      {
        id: "55555555-5555-4555-8555-555555555555",
        profile_id: creatorProfileId,
        version_number: 1,
        content_snapshot: { name: "creator-profile" },
        change_summary: "Initial profile creation",
        created_by: "user-a11y",
        created_at: timestamp,
      },
    ],
    next_cursor: null,
  });
  await fulfillJson(page, "**/api/v1/trust/contracts/schema", {
    type: "object",
    properties: {
      agent_id: { type: "string" },
      task_scope: { type: "string" },
    },
  });
  await fulfillJson(page, "**/api/v1/trust/contracts/schema-enums", {
    resource_types: ["workspace", "agent_revision"],
    role_types: ["executor", "planner"],
    workspace_constraints: ["workspace_visibility"],
    failure_modes: ["continue", "warn", "throttle", "escalate", "terminate"],
  });
  await fulfillJson(page, "**/api/v1/trust/contracts/templates", {
    items: [
      {
        id: creatorTemplateId,
        name: "Customer support agent contract",
        description: "Baseline contract for support agents.",
        category: "customer-support",
        template_content: {},
        version_number: 1,
        forked_from_template_id: null,
        created_by_user_id: null,
        is_platform_authored: true,
        is_published: true,
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
    total: 1,
  });
  await fulfillJson(page, `**/api/v1/trust/contracts/${creatorContractId}`, {
    id: creatorContractId,
    workspace_id: workspaceId,
    agent_id: "creator-ui:agent",
    task_scope: "Answer customer questions using approved sources.",
    expected_outputs: { required: ["answer", "citations"] },
    quality_thresholds: { minimum_confidence: 0.72 },
    time_constraint_seconds: null,
    cost_limit_tokens: null,
    escalation_conditions: { pii_detected: "escalate" },
    success_criteria: { must_include_citation: true },
    enforcement_policy: "warn",
    is_archived: false,
    attached_revision_id: null,
    created_at: timestamp,
    updated_at: timestamp,
  });
}

export function runA11yGroup(group: A11ySurfaceGroup) {
  for (const surface of surfacesForGroup(group)) {
    test(`${surface.id} has no WCAG 2.1 AA violations @a11y`, async ({ page }, testInfo) => {
      const { theme, locale } = contextFromProject(testInfo.project.name);
      await mockA11yApis(page);
      await installA11yState(page, theme, locale);
      await page.goto(`${surface.route}${surface.route.includes("?") ? "&" : "?"}lang=${locale}`);
      await surface.ready(page);
      await page.locator("html").evaluate((html, theme) => {
        html.classList.remove("light", "dark", "system", "high_contrast");
        if (theme !== "system") {
          html.classList.add(String(theme));
        }
      }, theme);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations).toEqual([]);
    });
  }
}

export { auditedSurfaces };
