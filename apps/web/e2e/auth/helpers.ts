import type { Page, Route } from "@playwright/test";

interface MockAuthOptions {
  loginMode?: "success" | "mfa" | "invalid" | "locked";
  mfaEnrolled?: boolean;
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
