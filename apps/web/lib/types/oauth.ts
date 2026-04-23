export type OAuthProviderType = "google" | "github";

export interface OAuthProviderPublic {
  provider_type: OAuthProviderType;
  display_name: string;
}

export interface OAuthProviderPublicListResponse {
  providers: OAuthProviderPublic[];
}

export interface OAuthProviderAdminResponse {
  id: string;
  provider_type: OAuthProviderType;
  display_name: string;
  enabled: boolean;
  client_id: string;
  client_secret_ref: string;
  redirect_uri: string;
  scopes: string[];
  domain_restrictions: string[];
  org_restrictions: string[];
  group_role_mapping: Record<string, string>;
  default_role: string;
  require_mfa: boolean;
  created_at: string;
  updated_at: string;
}

export interface OAuthProviderAdminListResponse {
  providers: OAuthProviderAdminResponse[];
}

export interface OAuthProviderUpsertRequest {
  display_name: string;
  enabled: boolean;
  client_id: string;
  client_secret_ref: string;
  redirect_uri: string;
  scopes: string[];
  domain_restrictions: string[];
  org_restrictions: string[];
  group_role_mapping: Record<string, string>;
  default_role: string;
  require_mfa: boolean;
}

export interface OAuthLinkResponse {
  provider_type: OAuthProviderType;
  display_name: string;
  linked_at: string;
  last_login_at: string | null;
  external_email: string | null;
  external_name: string | null;
  external_avatar_url: string | null;
}

export interface OAuthLinkListResponse {
  items: OAuthLinkResponse[];
}

export interface OAuthAuthorizeResponse {
  redirect_url: string;
}
