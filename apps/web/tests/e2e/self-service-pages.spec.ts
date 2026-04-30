import { expect, test, type Page, type Route } from "@playwright/test";

const now = "2026-04-30T10:00:00.000Z";
const userId = "11111111-1111-4111-8111-111111111111";
const alertId = "22222222-2222-4222-8222-222222222222";
const apiKeyId = "33333333-3333-4333-8333-333333333333";
const consentId = "44444444-4444-4444-8444-444444444444";
const dsrId = "55555555-5555-4555-8555-555555555555";
const sessionId = "66666666-6666-4666-8666-666666666666";

async function fulfillJson(route: Route, payload: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function installAuth(page: Page, mfaEnrolled = true) {
  await page.addInitScript(
    ({ mfaEnrolled, userId }) => {
      window.localStorage.setItem(
        "auth-storage",
        JSON.stringify({
          state: {
            user: {
              id: userId,
              email: "self-service@musematic.dev",
              displayName: "Self Service",
              avatarUrl: null,
              roles: ["workspace_admin"],
              workspaceId: "77777777-7777-4777-8777-777777777777",
              mfaEnrolled,
            },
            accessToken: "mock-access-token",
            refreshToken: "mock-refresh-token",
            isAuthenticated: true,
            isLoading: false,
          },
          version: 0,
        }),
      );
    },
    { mfaEnrolled, userId },
  );
}

async function mockSelfServiceApis(page: Page) {
  const alertPayload = {
    items: [
      {
        id: alertId,
        alert_type: "security.session",
        title: "New security alert",
        body: "A new sign-in was detected.",
        urgency: "critical",
        read: false,
        interaction_id: null,
        source_reference: { channel: "in_app", url: "/settings/security/activity" },
        created_at: now,
        updated_at: now,
      },
    ],
    next_cursor: null,
    total_unread: 1,
  };

  await page.route("**/api/v1/workspaces", (route) =>
    fulfillJson(route, { items: [] }),
  );
  await page.route("**/api/v1/me/preferences", (route) =>
    fulfillJson(route, {
      id: "prefs-1",
      user_id: userId,
      default_workspace_id: null,
      theme: "system",
      language: "en",
      timezone: "UTC",
      notification_preferences: {},
      data_export_format: "json",
      is_persisted: true,
      created_at: now,
      updated_at: now,
    }),
  );
  await page.route("**/me/alerts/unread-count", (route) =>
    fulfillJson(route, { count: 1 }),
  );
  await page.route("**/me/alerts**", (route) => fulfillJson(route, alertPayload));
  await page.route("**/api/v1/me/alerts/mark-all-read", (route) =>
    fulfillJson(route, { updated: 1, unread_count: 0 }),
  );
  await page.route("**/api/v1/me/alerts**", (route) => fulfillJson(route, alertPayload));
  await page.route("**/api/v1/me/notification-preferences/test/**", (route) =>
    fulfillJson(route, {
      alert_id: alertId,
      event_type: "security.session",
      delivery_method: "in_app",
      success: true,
    }),
  );
  await page.route("**/api/v1/me/notification-preferences", (route) => {
    if (route.request().method() === "PUT") {
      return fulfillJson(route, {
        state_transitions: [],
        delivery_method: "in_app",
        webhook_url: null,
        per_channel_preferences: {
          "security.session": ["in_app"],
          "incidents.resolved": ["in_app"],
        },
        digest_mode: { email: "daily" },
        quiet_hours: {
          start_time: "22:00",
          end_time: "07:00",
          timezone: "Europe/Madrid",
        },
      });
    }
    return fulfillJson(route, {
      state_transitions: [],
      delivery_method: "in_app",
      webhook_url: null,
      per_channel_preferences: {
        "security.session": ["in_app"],
        "incidents.resolved": ["in_app"],
      },
      digest_mode: { email: "daily" },
      quiet_hours: null,
    });
  });
  await page.route("**/api/v1/me/service-accounts", (route) => {
    if (route.request().method() === "POST") {
      return fulfillJson(route, {
        service_account_id: apiKeyId,
        name: "CLI token",
        role: "service_account",
        api_key: "msk_once_visible_value",
      });
    }
    return fulfillJson(route, {
      max_active: 10,
      items: [
        {
          service_account_id: apiKeyId,
          name: "Existing token",
          role: "service_account",
          status: "active",
          workspace_id: null,
          created_at: now,
          last_used_at: null,
          api_key_prefix: "msk_...abcd",
        },
      ],
    });
  });
  await page.route("**/api/v1/me/service-accounts/*", (route) =>
    fulfillJson(route, {}),
  );
  await page.route("**/api/v1/auth/mfa/enroll", (route) =>
    fulfillJson(route, {
      provisioning_uri:
        "otpauth://totp/Musematic:self-service%40musematic.dev?secret=JBSWY3DPEHPK3PXP&issuer=Musematic",
      secret: "JBSWY3DPEHPK3PXP",
      recovery_codes: ["alpha-bravo", "charlie-delta"],
    }),
  );
  await page.route("**/api/v1/auth/mfa/confirm", (route) =>
    fulfillJson(route, { status: "active", message: "MFA enrollment confirmed" }),
  );
  await page.route("**/api/v1/auth/mfa/recovery-codes/regenerate", (route) =>
    fulfillJson(route, { recovery_codes: ["echo-foxtrot", "golf-hotel"] }),
  );
  await page.route("**/api/v1/auth/mfa/disable", (route) =>
    fulfillJson(route, { status: "disabled", message: "MFA disabled" }),
  );
  await page.route("**/api/v1/me/sessions/revoke-others", (route) =>
    fulfillJson(route, { sessions_revoked: 2 }),
  );
  await page.route("**/api/v1/me/sessions/*", (route) => fulfillJson(route, {}));
  await page.route("**/api/v1/me/sessions", (route) =>
    fulfillJson(route, {
      items: [
        {
          session_id: sessionId,
          device_info: "Chrome on macOS",
          ip_address: "203.0.113.42",
          location: "Madrid",
          created_at: now,
          last_activity: now,
          is_current: true,
        },
        {
          session_id: "66666666-6666-4666-8666-777777777777",
          device_info: "Mobile Safari",
          ip_address: "203.0.113.43",
          location: "Barcelona",
          created_at: now,
          last_activity: now,
          is_current: false,
        },
      ],
    }),
  );
  await page.route("**/api/v1/me/activity**", (route) =>
    fulfillJson(route, {
      next_cursor: null,
      items: [
        {
          id: "88888888-8888-4888-8888-888888888888",
          event_type: "auth.session.revoked",
          audit_event_source: "auth",
          severity: "info",
          created_at: now,
          canonical_payload: {},
        },
      ],
    }),
  );
  await page.route("**/api/v1/me/consent/history", (route) =>
    fulfillJson(route, {
      items: [
        {
          id: consentId,
          consent_type: "ai_interaction",
          granted: false,
          granted_at: now,
          revoked_at: now,
          workspace_id: null,
        },
      ],
    }),
  );
  await page.route("**/api/v1/me/consent/revoke", (route) => fulfillJson(route, {}));
  await page.route("**/api/v1/me/consent", (route) =>
    fulfillJson(route, {
      items: [
        {
          id: consentId,
          consent_type: "ai_interaction",
          granted: true,
          granted_at: now,
          revoked_at: null,
          workspace_id: null,
        },
      ],
    }),
  );
  await page.route("**/api/v1/me/dsr**", (route) => {
    if (route.request().method() === "POST") {
      return fulfillJson(route, {
        id: dsrId,
        subject_user_id: userId,
        request_type: "access",
        requested_by: userId,
        status: "received",
        legal_basis: null,
        scheduled_release_at: null,
        requested_at: now,
        completed_at: null,
        completion_proof_hash: null,
        failure_reason: null,
        tombstone_id: null,
      });
    }
    return fulfillJson(route, {
      next_cursor: null,
      items: [
        {
          id: dsrId,
          subject_user_id: userId,
          request_type: "access",
          requested_by: userId,
          status: "received",
          legal_basis: null,
          scheduled_release_at: null,
          requested_at: now,
          completed_at: null,
          completion_proof_hash: null,
          failure_reason: null,
          tombstone_id: null,
        },
      ],
    });
  });
}

test.beforeEach(async ({ page }) => {
  await mockSelfServiceApis(page);
});

test("notification bell and inbox support catch-up and bulk read flows", async ({ page }) => {
  await installAuth(page);
  await page.goto("/notifications");

  await expect(page.getByRole("button", { name: /notifications/i })).toBeVisible();
  await page.getByRole("button", { name: /notifications/i }).click();
  await expect(page.getByText("New security alert").first()).toBeVisible();
  await page.getByText("See all").click();
  await expect(page).toHaveURL(/\/notifications/);
  await expect(page.getByRole("heading", { name: /notifications/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "New security alert" })).toBeVisible();
  await page.getByRole("button", { name: /mark all read/i }).click();
});

test("notification preferences persist matrix, digest, quiet hours, and test notification", async ({
  page,
}) => {
  await installAuth(page);
  await page.goto("/settings/notifications");

  await expect(page.getByRole("heading", { name: /notification preferences/i })).toBeVisible();
  await expect(page.getByText("security.login").first()).toBeVisible();
  await page.getByRole("button", { name: /save/i }).click();
  await page.getByRole("button", { name: /test/i }).first().click();
});

test("API keys can be created once, displayed once, and revoked", async ({ page }) => {
  await installAuth(page);
  await page.goto("/settings/api-keys");

  await expect(page.getByRole("heading", { name: /api keys/i })).toBeVisible();
  await page.getByRole("button", { name: /create/i }).click();
  await page.getByLabel(/name/i).fill("CLI token");
  await page.getByLabel(/mfa code/i).fill("123456");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByText("msk_once_visible_value")).toBeVisible();
  await page.getByRole("button", { name: /dismiss/i }).click();
  await page.getByRole("button", { name: /revoke/i }).first().click();
});

test("MFA page supports enrollment, backup-code regeneration, and disable", async ({ page }) => {
  await installAuth(page, false);
  await page.goto("/settings/security/mfa");

  await page.getByRole("button", { name: /start enrollment/i }).click();
  await expect(page.getByText(/manual entry/i)).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByLabel(/authenticator verification code/i).fill("123456");
  await expect(page.getByText(/one-time backup codes/i)).toBeVisible();
  await page.getByLabel(/saved these backup codes/i).check();
  await page.getByRole("button", { name: /saved them/i }).click();

  await page.getByRole("button", { name: /regenerate backup codes/i }).click();
  await page.getByLabel(/backup-code regeneration/i).fill("123456");
  await page.getByRole("button", { name: /^regenerate$/i }).click();
  await expect(page.getByText("echo-foxtrot")).toBeVisible();
  await page.getByLabel(/saved these backup codes/i).check();
  await page.getByRole("button", { name: /saved them/i }).click();

  await page.getByRole("button", { name: /disable mfa/i }).click();
  await page.getByLabel(/^password$/i).fill("correct horse battery staple");
  await page.getByLabel(/disabling mfa/i).fill("123456");
  await page.getByRole("dialog").getByRole("button", { name: /^disable mfa$/i }).click();
});

test("sessions and activity pages render scoped self-service data", async ({ page }) => {
  await installAuth(page);
  await page.goto("/settings/security/sessions");
  await expect(page.getByText("Chrome on macOS")).toBeVisible();
  await expect(page.getByText(/this session/i)).toBeVisible();
  await page.getByRole("button", { name: /revoke other sessions/i }).click();

  await page.goto("/settings/security/activity");
  await expect(page.getByText("auth.session.revoked")).toBeVisible();
});

test("consent management supports consequence dialog and history", async ({ page }) => {
  await installAuth(page);
  await page.goto("/settings/privacy/consent");

  await expect(page.getByRole("heading", { name: "ai_interaction" })).toBeVisible();
  await page.getByRole("button", { name: /revoke/i }).click();
  await expect(page.getByText(/related agent interactions/i)).toBeVisible();
  await page.getByRole("button", { name: /revoke consent/i }).click();
  await page.getByRole("button", { name: /history/i }).click();
  await expect(page.getByText(/revoked/i)).toBeVisible();
});

test("DSR self-service supports access and erasure typed confirmation", async ({ page }) => {
  await installAuth(page);
  await page.goto("/settings/privacy/dsr");

  await expect(page.getByRole("heading", { name: /data subject requests/i })).toBeVisible();
  await page.getByLabel(/request type/i).selectOption("access");
  await page.getByRole("button", { name: /submit/i }).click();
  await expect(page.getByText(/received/i)).toBeVisible();

  await page.getByLabel(/request type/i).selectOption("erasure");
  await page.getByLabel(/type delete/i).fill("DELETE");
  await expect(page.getByRole("button", { name: /submit/i })).toBeEnabled();
});
