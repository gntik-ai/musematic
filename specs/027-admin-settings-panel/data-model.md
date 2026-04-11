# Data Model: Admin Settings Panel

**Branch**: `027-admin-settings-panel` | **Date**: 2026-04-12 | **Phase**: 1

Frontend-only feature. Documents TypeScript types, Zod schemas, component props, and custom hooks.

---

## TypeScript Types

```typescript
// apps/web/lib/types/admin.ts

// --- Users Tab ---
export type UserStatus = "pending_verification" | "pending_approval" | "active" | "suspended" | "blocked" | "archived";
export type UserRole = "platform_admin" | "workspace_owner" | "workspace_admin" | "workspace_member" | "workspace_viewer";

export interface AdminUserRow {
  id: string;
  name: string;
  email: string;
  status: UserStatus;
  role: UserRole;
  last_login_at: string | null;     // ISO 8601
  created_at: string;               // ISO 8601
  available_actions: UserAction[];  // Backend-computed based on current status
}

export type UserAction = "approve" | "reject" | "suspend" | "reactivate";

export interface AdminUsersResponse {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
}

// --- Signup Tab ---
export type SignupMode = "open" | "invite_only" | "admin_approval";
export type MFAEnforcement = "optional" | "required";

export interface SignupPolicySettings {
  signup_mode: SignupMode;
  mfa_enforcement: MFAEnforcement;
  updated_at: string;               // For optimistic concurrency
}

// --- Quotas Tab ---
export interface DefaultQuotas {
  max_agents: number;
  max_concurrent_executions: number;
  max_sandboxes: number;
  monthly_token_budget: number;     // In thousands (e.g., 1000 = 1M tokens)
  storage_quota_gb: number;
  updated_at: string;
}

export interface WorkspaceQuotaOverride {
  workspace_id: string;
  workspace_name: string;
  max_agents: number | null;        // null = inherit default
  max_concurrent_executions: number | null;
  max_sandboxes: number | null;
  monthly_token_budget: number | null;
  storage_quota_gb: number | null;
  updated_at: string;
}

// --- Connectors Tab ---
export interface ConnectorTypeGlobalConfig {
  slug: string;                     // "slack", "telegram", "webhook", "email"
  display_name: string;
  description: string;
  is_enabled: boolean;
  active_instance_count: number;    // Number of existing instances (for warning on disable)
  max_payload_size_bytes: number;   // Default max payload size
  default_retry_count: number;
  updated_at: string;
}

// --- Email Tab ---
export type EmailMode = "smtp" | "ses";

export interface EmailDeliveryConfig {
  mode: EmailMode;
  smtp?: {
    host: string;
    port: number;
    username: string;
    password_set: boolean;          // True if password is configured (never returned as plaintext)
    encryption: "tls" | "starttls" | "none";
  };
  ses?: {
    region: string;
    access_key_id: string;
    secret_access_key_set: boolean; // True if secret is configured
  };
  from_address: string;
  from_name: string;
  verification_status: "verified" | "unverified" | "error";
  last_delivery_at: string | null;
  updated_at: string;
}

// --- Security Tab ---
export interface SecurityPolicySettings {
  password_min_length: number;       // Default: 12
  password_require_uppercase: boolean;
  password_require_lowercase: boolean;
  password_require_digit: boolean;
  password_require_special: boolean;
  password_expiry_days: number | null; // null = no expiry
  session_duration_minutes: number;   // Default: 480 (8 hours)
  lockout_max_attempts: number;       // Default: 5
  lockout_duration_minutes: number;   // Default: 15
  updated_at: string;
}
```

---

## Zod Validation Schemas

```typescript
// apps/web/lib/schemas/admin.ts

import { z } from "zod";

export const signupPolicySchema = z.object({
  signup_mode: z.enum(["open", "invite_only", "admin_approval"]),
  mfa_enforcement: z.enum(["optional", "required"]),
});

export const defaultQuotasSchema = z.object({
  max_agents: z.number().int().min(1).max(10_000),
  max_concurrent_executions: z.number().int().min(1).max(1_000),
  max_sandboxes: z.number().int().min(0).max(500),
  monthly_token_budget: z.number().int().min(0),  // 0 = unlimited
  storage_quota_gb: z.number().int().min(1).max(10_000),
});

export const workspaceQuotaOverrideSchema = z.object({
  max_agents: z.number().int().min(1).max(10_000).nullable(),
  max_concurrent_executions: z.number().int().min(1).max(1_000).nullable(),
  max_sandboxes: z.number().int().min(0).max(500).nullable(),
  monthly_token_budget: z.number().int().min(0).nullable(),
  storage_quota_gb: z.number().int().min(1).max(10_000).nullable(),
});

export const emailSmtpSchema = z.object({
  mode: z.literal("smtp"),
  host: z.string().min(1, "Host is required"),
  port: z.number().int().min(1).max(65535),
  username: z.string().min(1, "Username is required"),
  new_password: z.string().optional(),   // Only present when updating credential
  encryption: z.enum(["tls", "starttls", "none"]),
  from_address: z.string().email("Valid email required"),
  from_name: z.string().min(1, "From name is required"),
});

export const emailSesSchema = z.object({
  mode: z.literal("ses"),
  region: z.string().min(1, "Region is required"),
  access_key_id: z.string().min(1, "Access key ID is required"),
  new_secret_access_key: z.string().optional(),
  from_address: z.string().email("Valid email required"),
  from_name: z.string().min(1, "From name is required"),
});

export const emailConfigSchema = z.discriminatedUnion("mode", [emailSmtpSchema, emailSesSchema]);

export const securityPolicySchema = z.object({
  password_min_length: z.number().int().min(8, "Minimum 8 characters").max(128),
  password_require_uppercase: z.boolean(),
  password_require_lowercase: z.boolean(),
  password_require_digit: z.boolean(),
  password_require_special: z.boolean(),
  password_expiry_days: z.number().int().min(1).max(365).nullable(),
  session_duration_minutes: z.number().int().min(15, "Minimum 15 minutes").max(43200, "Maximum 30 days"),
  lockout_max_attempts: z.number().int().min(1, "Minimum 1 attempt").max(20),
  lockout_duration_minutes: z.number().int().min(1).max(1440, "Maximum 24 hours"),
});

export const testEmailSchema = z.object({
  recipient: z.string().email("Valid email address required"),
});
```

---

## Query Key Factories

```typescript
// apps/web/lib/hooks/use-admin-settings.ts

export const adminQueryKeys = {
  users: (params: AdminUsersParams) => ["admin", "users", params] as const,
  signupPolicy: () => ["admin", "settings", "signup"] as const,
  defaultQuotas: () => ["admin", "settings", "quotas"] as const,
  workspaceQuota: (wsId: string) => ["admin", "settings", "quotas", wsId] as const,
  connectorTypes: () => ["admin", "settings", "connectors"] as const,
  emailConfig: () => ["admin", "settings", "email"] as const,
  securityPolicy: () => ["admin", "settings", "security"] as const,
};
```

---

## Custom Hooks

```typescript
// apps/web/lib/hooks/use-admin-settings.ts

interface AdminUsersParams {
  search?: string;
  status?: UserStatus;
  page?: number;
  sort?: string;
}

// Users Tab
export function useAdminUsers(params: AdminUsersParams) {
  return useQuery({
    queryKey: adminQueryKeys.users(params),
    queryFn: () => api.get<AdminUsersResponse>(`/api/v1/admin/users`, { params }),
    staleTime: 30_000,
  });
}

export function useUserActionMutation(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: UserAction) =>
      api.post(`/api/v1/admin/users/${userId}/${action}`),
    onMutate: async (action) => {
      // Optimistic status update
      await queryClient.cancelQueries({ queryKey: ["admin", "users"] });
      // ... optimistic update logic
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

// Signup Policy
export function useSignupPolicy() {
  return useQuery({
    queryKey: adminQueryKeys.signupPolicy(),
    queryFn: () => api.get<SignupPolicySettings>("/api/v1/admin/settings/signup"),
  });
}

export function useSignupPolicyMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: z.infer<typeof signupPolicySchema> & { _version: string }) =>
      api.patch("/api/v1/admin/settings/signup", data, {
        headers: { "If-Unmodified-Since": data._version },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminQueryKeys.signupPolicy() });
    },
  });
}

// Default Quotas
export function useDefaultQuotas() {
  return useQuery({
    queryKey: adminQueryKeys.defaultQuotas(),
    queryFn: () => api.get<DefaultQuotas>("/api/v1/admin/settings/quotas"),
  });
}

// Workspace Quota Override
export function useWorkspaceQuota(workspaceId: string) {
  return useQuery({
    queryKey: adminQueryKeys.workspaceQuota(workspaceId),
    queryFn: () => api.get<WorkspaceQuotaOverride>(
      `/api/v1/admin/settings/quotas/workspaces/${workspaceId}`
    ),
    enabled: !!workspaceId,
  });
}

// Connector Types (global config)
export function useConnectorTypeConfigs() {
  return useQuery({
    queryKey: adminQueryKeys.connectorTypes(),
    queryFn: () => api.get<ConnectorTypeGlobalConfig[]>("/api/v1/admin/settings/connectors"),
  });
}

export function useConnectorTypeToggleMutation(typeSlug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      api.patch(`/api/v1/admin/settings/connectors/${typeSlug}`, { is_enabled: enabled }),
    onMutate: async (enabled) => {
      // Optimistic toggle update
      await queryClient.cancelQueries({ queryKey: adminQueryKeys.connectorTypes() });
      const previous = queryClient.getQueryData(adminQueryKeys.connectorTypes());
      queryClient.setQueryData(adminQueryKeys.connectorTypes(), (old: ConnectorTypeGlobalConfig[]) =>
        old.map(c => c.slug === typeSlug ? { ...c, is_enabled: enabled } : c)
      );
      return { previous };
    },
    onError: (_, __, context) => {
      queryClient.setQueryData(adminQueryKeys.connectorTypes(), context?.previous);
    },
  });
}

// Email Config
export function useEmailConfig() {
  return useQuery({
    queryKey: adminQueryKeys.emailConfig(),
    queryFn: () => api.get<EmailDeliveryConfig>("/api/v1/admin/settings/email"),
  });
}

export function useSendTestEmailMutation() {
  return useMutation({
    mutationFn: (recipient: string) =>
      api.post("/api/v1/admin/settings/email/test", { recipient }),
  });
}

// Security Policy
export function useSecurityPolicy() {
  return useQuery({
    queryKey: adminQueryKeys.securityPolicy(),
    queryFn: () => api.get<SecurityPolicySettings>("/api/v1/admin/settings/security"),
  });
}
```

---

## Component Props

```typescript
// apps/web/components/features/admin/

// AdminSettingsPanel.tsx ("use client" root)
interface AdminSettingsPanelProps {
  defaultTab?: string;  // From URL search param
}

// tabs/UsersTab.tsx
interface UsersTabProps {}

// tabs/SignupPolicyTab.tsx
interface SignupPolicyTabProps {}

// tabs/QuotasTab.tsx
interface QuotasTabProps {}

// tabs/ConnectorsTab.tsx
interface ConnectorsTabProps {}

// tabs/EmailTab.tsx
interface EmailTabProps {}

// tabs/SecurityTab.tsx
interface SecurityTabProps {}

// users/UserActionsMenu.tsx
interface UserActionsMenuProps {
  user: AdminUserRow;
  onActionComplete: () => void;
}

// users/UserActionDialog.tsx
interface UserActionDialogProps {
  user: AdminUserRow;
  action: UserAction;
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}

// connectors/ConnectorTypeCard.tsx
interface ConnectorTypeCardProps {
  config: ConnectorTypeGlobalConfig;
}

// shared/StaleDataAlert.tsx
interface StaleDataAlertProps {
  onReload: () => void;
}

// shared/SettingsFormActions.tsx
interface SettingsFormActionsProps {
  isDirty: boolean;
  isPending: boolean;
  isSaved: boolean;           // Briefly true after successful save
  onReset: () => void;
}
```
