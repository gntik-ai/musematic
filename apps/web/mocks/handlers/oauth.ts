import { http, HttpResponse } from "msw";
import type {
  OAuthHistoryEntryResponse,
  OAuthLinkResponse,
  OAuthProviderAdminResponse,
  OAuthProviderStatusResponse,
  OAuthProviderType,
  OAuthRateLimitConfig,
} from "@/lib/types/oauth";

function nowVersion(): string {
  return new Date().toISOString();
}

function buildProvider(
  providerType: OAuthProviderType,
  overrides: Partial<OAuthProviderAdminResponse> = {},
): OAuthProviderAdminResponse {
  const baseScopes =
    providerType === "google"
      ? ["openid", "email", "profile"]
      : ["read:user", "user:email"];

  return {
    id: `${providerType}-provider-id`,
    provider_type: providerType,
    display_name: providerType === "google" ? "Google" : "GitHub",
    enabled: providerType === "google",
    client_id: `${providerType}-client-id`,
    client_secret_ref: `secret://${providerType}`,
    redirect_uri: `https://app.musematic.dev/oauth/${providerType}/callback`,
    scopes: baseScopes,
    domain_restrictions: providerType === "google" ? ["musematic.dev"] : [],
    org_restrictions: providerType === "github" ? ["musematic"] : [],
    group_role_mapping: { admins: "platform_admin" },
    default_role: "viewer",
    require_mfa: false,
    source: "manual",
    last_edited_by: null,
    last_edited_at: null,
    last_successful_auth_at: null,
    created_at: "2026-04-18T07:00:00.000Z",
    updated_at: nowVersion(),
    ...overrides,
  };
}

function buildLink(
  providerType: OAuthProviderType,
  overrides: Partial<OAuthLinkResponse> = {},
): OAuthLinkResponse {
  return {
    provider_type: providerType,
    display_name: providerType === "google" ? "Google" : "GitHub",
    linked_at: "2026-04-17T08:00:00.000Z",
    last_login_at: "2026-04-18T07:30:00.000Z",
    external_email:
      providerType === "google"
        ? "alex@musematic.dev"
        : "octocat@musematic.dev",
    external_name: providerType === "google" ? "Alex Mercer" : "Octo Cat",
    external_avatar_url: null,
    ...overrides,
  };
}

export interface OAuthMockState {
  history: Record<OAuthProviderType, OAuthHistoryEntryResponse[]>;
  links: OAuthLinkResponse[];
  providers: Record<OAuthProviderType, OAuthProviderAdminResponse>;
  rateLimits: Record<OAuthProviderType, OAuthRateLimitConfig>;
}

export function createOAuthMockState(): OAuthMockState {
  return {
    history: {
      github: [],
      google: [
        {
          timestamp: "2026-04-18T07:15:00.000Z",
          admin_id: null,
          action: "provider_bootstrapped",
          before: null,
          after: { enabled: true, source: "env_var" },
        },
      ],
    },
    links: [buildLink("google")],
    providers: {
      github: buildProvider("github", { enabled: true }),
      google: buildProvider("google", {
        enabled: true,
        source: "env_var",
        last_successful_auth_at: "2026-04-18T07:30:00.000Z",
      }),
    },
    rateLimits: {
      github: {
        per_ip_max: 10,
        per_ip_window: 60,
        per_user_max: 10,
        per_user_window: 60,
        global_max: 100,
        global_window: 60,
      },
      google: {
        per_ip_max: 10,
        per_ip_window: 60,
        per_user_max: 10,
        per_user_window: 60,
        global_max: 100,
        global_window: 60,
      },
    },
  };
}

export const oauthFixtures = createOAuthMockState();

export function resetOAuthFixtures(): void {
  const fresh = createOAuthMockState();
  oauthFixtures.history = fresh.history;
  oauthFixtures.links = fresh.links;
  oauthFixtures.providers = fresh.providers;
  oauthFixtures.rateLimits = fresh.rateLimits;
}

function getProvider(providerType: string): OAuthProviderAdminResponse | undefined {
  return oauthFixtures.providers[providerType as OAuthProviderType];
}

export const oauthHandlers = [
  http.get("*/api/v1/auth/oauth/providers", () => {
    const providers = Object.values(oauthFixtures.providers)
      .filter((provider) => provider.enabled)
      .map((provider) => ({
        display_name: provider.display_name,
        provider_type: provider.provider_type,
      }));

    return HttpResponse.json({ providers });
  }),
  http.get("*/api/v1/auth/oauth/links", () =>
    HttpResponse.json({ items: oauthFixtures.links }),
  ),
  http.get("*/api/v1/auth/oauth/:provider/authorize", ({ params }) => {
    const provider = getProvider(String(params.provider));
    if (!provider || !provider.enabled) {
      return HttpResponse.json(
        {
          error: {
            code: "OAUTH_PROVIDER_DISABLED",
            message: "Provider is not enabled",
          },
        },
        { status: 403 },
      );
    }

    return HttpResponse.json({
      redirect_url: `https://oauth.example.com/${provider.provider_type}/authorize`,
    });
  }),
  http.post("*/api/v1/auth/oauth/:provider/link", ({ params }) => {
    const provider = getProvider(String(params.provider));
    if (!provider || !provider.enabled) {
      return HttpResponse.json(
        {
          error: {
            code: "OAUTH_PROVIDER_DISABLED",
            message: "Provider is not enabled",
          },
        },
        { status: 403 },
      );
    }

    return HttpResponse.json({
      redirect_url: `https://oauth.example.com/${provider.provider_type}/link`,
    });
  }),
  http.delete("*/api/v1/auth/oauth/:provider/link", ({ params }) => {
    const providerType = String(params.provider) as OAuthProviderType;
    const index = oauthFixtures.links.findIndex(
      (link) => link.provider_type === providerType,
    );

    if (index === -1) {
      return new HttpResponse(null, { status: 204 });
    }

    if (oauthFixtures.links.length <= 1) {
      return HttpResponse.json(
        {
          error: {
            code: "OAUTH_UNLINK_LAST_METHOD",
            message: "Cannot unlink the only authentication method",
          },
        },
        { status: 409 },
      );
    }

    oauthFixtures.links.splice(index, 1);
    return new HttpResponse(null, { status: 204 });
  }),
  http.get("*/api/v1/admin/oauth/providers", () =>
    HttpResponse.json({ providers: Object.values(oauthFixtures.providers) }),
  ),
  http.put("*/api/v1/admin/oauth/providers/:provider", async ({ params, request }) => {
    const providerType = String(params.provider) as OAuthProviderType;
    const current = getProvider(providerType) ?? buildProvider(providerType);
    const body = (await request.json()) as Omit<
      OAuthProviderAdminResponse,
      "id" | "provider_type" | "created_at" | "updated_at"
    >;

    oauthFixtures.providers[providerType] = {
      ...current,
      ...body,
      provider_type: providerType,
      updated_at: nowVersion(),
    };

    return HttpResponse.json(oauthFixtures.providers[providerType]);
  }),
  http.post("*/api/v1/admin/oauth-providers/:provider/test-connectivity", ({ params }) => {
    const provider = getProvider(String(params.provider));
    return HttpResponse.json({
      reachable: Boolean(provider),
      auth_url_returned: Boolean(provider?.enabled),
      diagnostic: provider?.enabled
        ? "authorization_url_generated"
        : "provider_not_enabled",
    });
  }),
  http.post("*/api/v1/admin/oauth-providers/:provider/rotate-secret", ({ params }) => {
    const providerType = String(params.provider) as OAuthProviderType;
    oauthFixtures.history[providerType].unshift({
      timestamp: nowVersion(),
      admin_id: "admin-user-id",
      action: "secret_rotated",
      before: null,
      after: { changed_fields: ["client_secret"] },
    });
    return new HttpResponse(null, { status: 204 });
  }),
  http.post("*/api/v1/admin/oauth-providers/:provider/reseed-from-env", async ({ params, request }) => {
    const providerType = String(params.provider) as OAuthProviderType;
    const body = (await request.json()) as { force_update?: boolean };
    const provider = getProvider(providerType);
    if (!provider) {
      return HttpResponse.json(
        {
          error: {
            code: "OAUTH_PROVIDER_NOT_FOUND",
            message: "Provider not found",
          },
        },
        { status: 404 },
      );
    }
    provider.source = "env_var";
    provider.updated_at = nowVersion();
    oauthFixtures.history[providerType].unshift({
      timestamp: nowVersion(),
      admin_id: "admin-user-id",
      action: "config_reseeded",
      before: { source: "manual" },
      after: { source: "env_var", force_update: Boolean(body.force_update) },
    });
    return HttpResponse.json({
      diff: {
        status: "updated",
        changed_fields: { source: "env_var", force_update: Boolean(body.force_update) },
      },
    });
  }),
  http.get("*/api/v1/admin/oauth-providers/:provider/history", ({ params }) => {
    const providerType = String(params.provider) as OAuthProviderType;
    return HttpResponse.json({
      entries: oauthFixtures.history[providerType] ?? [],
      next_cursor: null,
    });
  }),
  http.get("*/api/v1/admin/oauth-providers/:provider/status", ({ params }) => {
    const providerType = String(params.provider) as OAuthProviderType;
    const provider = getProvider(providerType);
    const response: OAuthProviderStatusResponse = {
      provider_type: providerType,
      source: provider?.source ?? "manual",
      last_successful_auth_at: provider?.last_successful_auth_at ?? null,
      auth_count_24h: providerType === "google" ? 3 : 0,
      auth_count_7d: providerType === "google" ? 11 : 0,
      auth_count_30d: providerType === "google" ? 27 : 0,
      active_linked_users: oauthFixtures.links.filter(
        (link) => link.provider_type === providerType,
      ).length,
    };
    return HttpResponse.json(response);
  }),
  http.get("*/api/v1/admin/oauth-providers/:provider/rate-limits", ({ params }) => {
    const providerType = String(params.provider) as OAuthProviderType;
    return HttpResponse.json(oauthFixtures.rateLimits[providerType]);
  }),
  http.put("*/api/v1/admin/oauth-providers/:provider/rate-limits", async ({ params, request }) => {
    const providerType = String(params.provider) as OAuthProviderType;
    const body = (await request.json()) as OAuthRateLimitConfig;
    oauthFixtures.rateLimits[providerType] = body;
    oauthFixtures.history[providerType].unshift({
      timestamp: nowVersion(),
      admin_id: "admin-user-id",
      action: "rate_limit_updated",
      before: null,
      after: { ...body },
    });
    return HttpResponse.json(body);
  }),
];
