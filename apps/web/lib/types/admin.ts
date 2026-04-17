import type { RoleType } from "@/types/auth";

export type UserStatus =
  | "pending_verification"
  | "pending_approval"
  | "active"
  | "suspended"
  | "blocked"
  | "archived";

export type UserRole = RoleType | "workspace_member";

export interface AdminUserRow {
  id: string;
  name: string;
  email: string;
  status: UserStatus;
  role: UserRole;
  last_login_at: string | null;
  created_at: string;
  available_actions: UserAction[];
}

export type UserAction = "approve" | "reject" | "suspend" | "reactivate";

export interface AdminUsersResponse {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
}

export type SignupMode = "open" | "invite_only" | "admin_approval";
export type MFAEnforcement = "optional" | "required";

export interface SignupPolicySettings {
  signup_mode: SignupMode;
  mfa_enforcement: MFAEnforcement;
  updated_at: string;
}

export interface DefaultQuotas {
  max_agents: number;
  max_concurrent_executions: number;
  max_sandboxes: number;
  monthly_token_budget: number;
  storage_quota_gb: number;
  updated_at: string;
}

export interface WorkspaceQuotaOverride {
  workspace_id: string;
  workspace_name: string;
  max_agents: number | null;
  max_concurrent_executions: number | null;
  max_sandboxes: number | null;
  monthly_token_budget: number | null;
  storage_quota_gb: number | null;
  updated_at: string;
}

export interface WorkspaceSearchItem {
  id: string;
  name: string;
}

export interface WorkspaceSearchResponse {
  items: WorkspaceSearchItem[];
  total: number;
}

export interface ConnectorTypeGlobalConfig {
  slug: string;
  display_name: string;
  description: string;
  is_enabled: boolean;
  active_instance_count: number;
  max_payload_size_bytes: number;
  default_retry_count: number;
  updated_at: string;
}

export type EmailMode = "smtp" | "ses";

export interface EmailSmtpConfig {
  host: string;
  port: number;
  username: string;
  password_set: boolean;
  encryption: "tls" | "starttls" | "none";
}

export interface EmailSesConfig {
  region: string;
  access_key_id: string;
  secret_access_key_set: boolean;
}

export interface EmailDeliveryConfig {
  mode: EmailMode;
  smtp?: EmailSmtpConfig;
  ses?: EmailSesConfig;
  from_address: string;
  from_name: string;
  verification_status: "verified" | "unverified" | "error";
  last_delivery_at: string | null;
  updated_at: string;
}

export interface TestEmailResult {
  success: boolean;
  message: string;
}

export interface SecurityPolicySettings {
  password_min_length: number;
  password_require_uppercase: boolean;
  password_require_lowercase: boolean;
  password_require_digit: boolean;
  password_require_special: boolean;
  password_expiry_days: number | null;
  session_duration_minutes: number;
  lockout_max_attempts: number;
  lockout_duration_minutes: number;
  updated_at: string;
}

export interface AdminUsersParams {
  search?: string;
  status?: UserStatus | "all";
  page?: number;
  page_size?: number;
  sort?: string;
}
