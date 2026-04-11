import { http, HttpResponse } from "msw";
import { homeHandlers } from "@/mocks/handlers/home";
import type { TokenPair, UserProfile } from "@/types/auth";
import type { Workspace } from "@/types/workspace";

const mockUser: UserProfile = {
  id: "4d1b0f76-a961-4f8d-8bcb-3f7d5f530001",
  email: "alex@musematic.dev",
  displayName: "Alex Mercer",
  avatarUrl: null,
  roles: ["workspace_admin", "agent_operator", "analytics_viewer"],
  workspaceId: "workspace-1",
  mfaEnrolled: true,
};

const mockTokenPair: TokenPair = {
  accessToken: "mock-access-token",
  refreshToken: "mock-refresh-token",
  expiresIn: 900,
};

const mockMfaSessionToken = "mfa-session-token";

function toLoginSuccess(user: UserProfile = mockUser) {
  return {
    access_token: mockTokenPair.accessToken,
    refresh_token: mockTokenPair.refreshToken,
    expires_in: mockTokenPair.expiresIn,
    user: {
      id: user.id,
      email: user.email,
      display_name: user.displayName,
      avatar_url: user.avatarUrl,
      roles: user.roles,
      workspace_id: user.workspaceId,
      mfa_enrolled: user.mfaEnrolled,
    },
  };
}

const workspaces: Workspace[] = [
  {
    id: "workspace-1",
    name: "Signal Lab",
    slug: "signal-lab",
    description: "Primary operations workspace",
    memberCount: 18,
    createdAt: "2026-04-10T09:00:00.000Z",
  },
  {
    id: "workspace-2",
    name: "Trust Foundry",
    slug: "trust-foundry",
    description: "Safety and governance programs",
    memberCount: 11,
    createdAt: "2026-04-08T13:30:00.000Z",
  },
];

const authHandlers = [
  http.post("*/api/v1/auth/login", async ({ request }) => {
    const body = (await request.json()) as { email?: string };
    if (body.email?.includes("mfa")) {
      return HttpResponse.json({
        mfa_required: true,
        session_token: mockMfaSessionToken,
      });
    }

    if (body.email?.includes("locked")) {
      return HttpResponse.json(
        {
          error: {
            code: "ACCOUNT_LOCKED",
            message: "Account locked",
            details: [{ message: "Account locked", field: "email" }],
            lockout_seconds: 90,
          },
        },
        { status: 429 },
      );
    }

    if (body.email?.includes("invalid")) {
      return HttpResponse.json(
        {
          error: {
            code: "INVALID_CREDENTIALS",
            message: "Invalid email or password",
          },
        },
        { status: 401 },
      );
    }

    return HttpResponse.json(toLoginSuccess());
  }),
  http.post("*/api/v1/auth/mfa/verify", async ({ request }) => {
    const body = (await request.json()) as { code?: string; use_recovery_code?: boolean };

    if (body.code === "654321" || body.code === "bad-code") {
      return HttpResponse.json(
        {
          error: {
            code: "INVALID_CODE",
            message: "Invalid verification code",
          },
        },
        { status: 401 },
      );
    }

    return HttpResponse.json({
      ...toLoginSuccess({
        ...mockUser,
        mfaEnrolled: true,
      }),
      recovery_code_consumed: body.use_recovery_code === true,
    });
  }),
  http.post("*/api/v1/auth/password-reset/request", async () => HttpResponse.json({}, { status: 202 })),
  http.post("*/api/v1/auth/password-reset/complete", async ({ request }) => {
    const body = (await request.json()) as { token?: string };
    if (body.token?.includes("expired") || body.token?.includes("used")) {
      return HttpResponse.json(
        {
          error: {
            code: body.token.includes("expired") ? "TOKEN_EXPIRED" : "TOKEN_ALREADY_USED",
            message: "Token is invalid",
          },
        },
        { status: 400 },
      );
    }

    return HttpResponse.json({ success: true });
  }),
  http.post("*/api/v1/auth/mfa/enroll", async () =>
    HttpResponse.json({
      provisioning_uri: "otpauth://totp/Musematic:alex%40musematic.dev?secret=JBSWY3DPEHPK3PXP&issuer=Musematic",
      secret_key: "JBSW Y3DP EHPK 3PXP",
    }),
  ),
  http.post("*/api/v1/auth/mfa/confirm", async ({ request }) => {
    const body = (await request.json()) as { code?: string };
    if (body.code === "000000") {
      return HttpResponse.json(
        {
          error: {
            code: "INVALID_CODE",
            message: "Incorrect code. Please try again.",
          },
        },
        { status: 401 },
      );
    }

    return HttpResponse.json({
      recovery_codes: [
        "alpha-bravo-charlie",
        "delta-echo-foxtrot",
        "golf-hotel-india",
        "juliet-kilo-lima",
        "mike-november-oscar",
        "papa-quebec-romeo",
        "sierra-tango-uniform",
        "victor-whiskey-xray",
        "yankee-zulu-axle",
        "binary-signal-aurora",
      ],
    });
  }),
  http.post("*/api/v1/auth/refresh", async () =>
    HttpResponse.json({
      access_token: mockTokenPair.accessToken,
      refresh_token: mockTokenPair.refreshToken,
      expires_in: mockTokenPair.expiresIn,
    }),
  ),
  http.post("*/api/v1/auth/logout", async () => new HttpResponse(null, { status: 204 })),
  http.get("*/api/v1/workspaces", async () => HttpResponse.json({ items: workspaces })),
];

export const handlers = [...authHandlers, ...homeHandlers];

export { mockMfaSessionToken, mockTokenPair, mockUser, toLoginSuccess, workspaces };
