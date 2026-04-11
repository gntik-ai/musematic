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

function createAdminState() {
  return {
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
    users: [
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
    ] satisfies AdminUserRecord[],
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
) {
  return users.map((user) => {
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
}
