export type OAuthProviderType = "google" | "github";
export type OAuthProviderSource = "env_var" | "manual" | "imported";

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
  source: OAuthProviderSource;
  last_edited_by: string | null;
  last_edited_at: string | null;
  last_successful_auth_at: string | null;
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

export interface OAuthConnectivityTestResponse {
  reachable: boolean;
  auth_url_returned: boolean;
  diagnostic: string;
}

export interface OAuthConfigReseedResponse {
  diff: {
    status?: string;
    changed_fields?: Record<string, unknown>;
    audit_event_id?: string | null;
    [key: string]: unknown;
  };
}

export interface OAuthRateLimitConfig {
  per_ip_max: number;
  per_ip_window: number;
  per_user_max: number;
  per_user_window: number;
  global_max: number;
  global_window: number;
}

export interface OAuthHistoryEntryResponse {
  timestamp: string;
  admin_id: string | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface OAuthHistoryListResponse {
  entries: OAuthHistoryEntryResponse[];
  next_cursor: string | null;
}

export interface OAuthProviderStatusResponse {
  provider_type: OAuthProviderType;
  source: OAuthProviderSource;
  last_successful_auth_at: string | null;
  auth_count_24h: number;
  auth_count_7d: number;
  auth_count_30d: number;
  active_linked_users: number;
}
