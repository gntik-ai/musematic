import { http, HttpResponse } from "msw";
import type {
  OAuthLinkResponse,
  OAuthProviderAdminResponse,
  OAuthProviderType,
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
  links: OAuthLinkResponse[];
  providers: Record<OAuthProviderType, OAuthProviderAdminResponse>;
}

export function createOAuthMockState(): OAuthMockState {
  return {
    links: [buildLink("google")],
    providers: {
      github: buildProvider("github", { enabled: true }),
      google: buildProvider("google", { enabled: true }),
    },
  };
}

export const oauthFixtures = createOAuthMockState();

export function resetOAuthFixtures(): void {
  const fresh = createOAuthMockState();
  oauthFixtures.links = fresh.links;
  oauthFixtures.providers = fresh.providers;
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
];
