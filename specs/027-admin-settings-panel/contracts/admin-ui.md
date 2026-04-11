# UI Contracts: Admin Settings Panel

**Branch**: `027-admin-settings-panel` | **Date**: 2026-04-12 | **Phase**: 1

Frontend-only feature. Documents API endpoints consumed, component interaction contracts, and WebSocket channel usage.

---

## API Endpoints Consumed

### Users Tab

#### `GET /api/v1/admin/users`
Fetch paginated, filtered, sorted user list.

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | `string?` | Filter by name or email (debounced 300ms) |
| `status` | `UserStatus?` | Filter by account status |
| `page` | `number?` | Page number (default: 1) |
| `page_size` | `number?` | Items per page (default: 20) |
| `sort` | `string?` | Sort field and direction (e.g., `created_at:desc`) |

**Response**: `AdminUsersResponse`
```typescript
{
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
}
```

**Error Codes**:
- `403` — Not a platform admin
- `422` — Invalid query parameters

---

#### `POST /api/v1/admin/users/{id}/approve`
Approve a user in `pending_approval` status.

**Path Parameters**: `id` — user UUID

**Request Body**: _(empty)_

**Response**: `204 No Content`

**Error Codes**:
- `403` — Not a platform admin
- `404` — User not found
- `409` — User is not in `pending_approval` status

---

#### `POST /api/v1/admin/users/{id}/reject`
Reject a user in `pending_approval` status (moves to `blocked`).

**Request Body**: _(empty)_

**Response**: `204 No Content`

**Error Codes**: Same as approve

---

#### `POST /api/v1/admin/users/{id}/suspend`
Suspend an active user.

**Request Body**: _(empty)_

**Response**: `204 No Content`

**Error Codes**:
- `403` — Not a platform admin, or admin attempting self-suspension
- `404` — User not found
- `409` — User is not in `active` status

---

#### `POST /api/v1/admin/users/{id}/reactivate`
Reactivate a suspended user.

**Request Body**: _(empty)_

**Response**: `204 No Content`

**Error Codes**:
- `403` — Not a platform admin
- `404` — User not found
- `409` — User is not in `suspended` status

---

### Signup Policy Tab

#### `GET /api/v1/admin/settings/signup`
Fetch current signup policy.

**Response**: `SignupPolicySettings`
```typescript
{
  signup_mode: "open" | "invite_only" | "admin_approval";
  mfa_enforcement: "optional" | "required";
  updated_at: string;  // ISO 8601 — used for If-Unmodified-Since
}
```

---

#### `PATCH /api/v1/admin/settings/signup`
Update signup policy.

**Request Headers**:
| Header | Value | Description |
|--------|-------|-------------|
| `If-Unmodified-Since` | ISO 8601 timestamp | Stale-data guard (optimistic concurrency) |

**Request Body**:
```typescript
{
  signup_mode: "open" | "invite_only" | "admin_approval";
  mfa_enforcement: "optional" | "required";
}
```

**Response**: `200 OK` with updated `SignupPolicySettings`

**Error Codes**:
- `403` — Not a platform admin
- `412` — Precondition Failed (another admin modified settings since form was loaded) → triggers `StaleDataAlert`
- `422` — Validation error

---

### Quotas Tab

#### `GET /api/v1/admin/settings/quotas`
Fetch default quota values.

**Response**: `DefaultQuotas`
```typescript
{
  max_agents: number;
  max_concurrent_executions: number;
  max_sandboxes: number;
  monthly_token_budget: number;    // In thousands (0 = unlimited)
  storage_quota_gb: number;
  updated_at: string;
}
```

---

#### `PATCH /api/v1/admin/settings/quotas`
Update default quotas.

**Request Headers**: `If-Unmodified-Since`

**Request Body**: Same shape as `DefaultQuotas` without `updated_at`

**Response**: `200 OK` with updated `DefaultQuotas`

**Error Codes**: `403`, `412`, `422`

---

#### `GET /api/v1/admin/settings/quotas/workspaces/{ws_id}`
Fetch per-workspace quota override.

**Response**: `WorkspaceQuotaOverride`
```typescript
{
  workspace_id: string;
  workspace_name: string;
  max_agents: number | null;
  max_concurrent_executions: number | null;
  max_sandboxes: number | null;
  monthly_token_budget: number | null;
  storage_quota_gb: number | null;
  updated_at: string;
}
```

---

#### `PATCH /api/v1/admin/settings/quotas/workspaces/{ws_id}`
Update per-workspace quota override.

**Request Headers**: `If-Unmodified-Since`

**Request Body**: Partial `WorkspaceQuotaOverride` (null fields inherit default)

**Response**: `200 OK` with updated `WorkspaceQuotaOverride`

**Error Codes**: `403`, `404` (workspace not found), `412`, `422`

---

#### `GET /api/v1/admin/workspaces` _(combobox search)_
Fetch workspace list for the quota override workspace selector.

**Query Parameters**: `search?: string`, `page_size?: number` (default: 20)

**Response**:
```typescript
{
  items: { id: string; name: string }[];
  total: number;
}
```

---

### Connectors Tab

#### `GET /api/v1/admin/settings/connectors`
Fetch global connector type configurations.

**Response**: `ConnectorTypeGlobalConfig[]`
```typescript
[{
  slug: string;
  display_name: string;
  description: string;
  is_enabled: boolean;
  active_instance_count: number;
  max_payload_size_bytes: number;
  default_retry_count: number;
  updated_at: string;
}]
```

---

#### `PATCH /api/v1/admin/settings/connectors/{type_slug}`
Toggle or update global connector type config.

**Request Body**:
```typescript
{
  is_enabled?: boolean;
  max_payload_size_bytes?: number;
  default_retry_count?: number;
}
```

**Response**: `200 OK` with updated `ConnectorTypeGlobalConfig`

**Error Codes**: `403`, `404` (unknown type slug), `422`

---

### Email Tab

#### `GET /api/v1/admin/settings/email`
Fetch email delivery configuration.

**Response**: `EmailDeliveryConfig`
```typescript
{
  mode: "smtp" | "ses";
  smtp?: {
    host: string;
    port: number;
    username: string;
    password_set: boolean;      // True if configured; plaintext never returned
    encryption: "tls" | "starttls" | "none";
  };
  ses?: {
    region: string;
    access_key_id: string;
    secret_access_key_set: boolean;
  };
  from_address: string;
  from_name: string;
  verification_status: "verified" | "unverified" | "error";
  last_delivery_at: string | null;
  updated_at: string;
}
```

---

#### `PATCH /api/v1/admin/settings/email`
Update email delivery configuration.

**Request Headers**: `If-Unmodified-Since`

**Request Body** (SMTP mode):
```typescript
{
  mode: "smtp";
  host: string;
  port: number;
  username: string;
  new_password?: string;        // Only present when updating credential
  encryption: "tls" | "starttls" | "none";
  from_address: string;
  from_name: string;
}
```

**Request Body** (SES mode):
```typescript
{
  mode: "ses";
  region: string;
  access_key_id: string;
  new_secret_access_key?: string;
  from_address: string;
  from_name: string;
}
```

**Response**: `200 OK` with updated `EmailDeliveryConfig`

**Error Codes**: `403`, `412`, `422`

---

#### `POST /api/v1/admin/settings/email/test`
Send a test email to verify configuration.

**Request Body**:
```typescript
{ recipient: string }  // Valid email address
```

**Response**:
```typescript
{
  success: boolean;
  message: string;   // e.g., "Test email sent successfully" or error description
}
```

**Error Codes**: `403`, `408` (timeout after 10s), `422`

---

### Security Tab

#### `GET /api/v1/admin/settings/security`
Fetch security policy.

**Response**: `SecurityPolicySettings`
```typescript
{
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
```

---

#### `PATCH /api/v1/admin/settings/security`
Update security policy.

**Request Headers**: `If-Unmodified-Since`

**Request Body**: Same shape as `SecurityPolicySettings` without `updated_at`

**Response**: `200 OK` with updated `SecurityPolicySettings`

**Error Codes**: `403`, `412`, `422`

---

## WebSocket Channel Usage

Admin Settings Panel does **not** subscribe to WebSocket channels. Settings are not expected to receive real-time push updates. Stale-data detection uses the `If-Unmodified-Since` / 412 pattern instead.

---

## Component Interaction Contracts

### `AdminSettingsPanel` → Tab Components

```
AdminSettingsPanel (client root)
├── reads: useSearchParams() → defaultTab
├── writes: router.push(`?tab=${tab}`) on tab change
└── renders: <Tabs value={currentTab}>
    ├── <UsersTab />
    ├── <SignupPolicyTab />
    ├── <QuotasTab />
    ├── <ConnectorsTab />
    ├── <EmailTab />
    └── <SecurityTab />
```

---

### `UsersTab` Component Contract

**Responsibilities**: Renders user DataTable, manages search/filter/sort state, triggers action dialogs.

**State**:
```typescript
searchValue: string         // Debounced 300ms before passed to useAdminUsers
statusFilter: UserStatus | undefined
page: number
sort: string

selectedUser: AdminUserRow | null
pendingAction: UserAction | null
```

**Child Components**:
- `DataTable` (scaffold) — server-side mode, columns defined inline
- `UserActionsMenu` — per-row dropdown, receives user + onAction callback
- `UserActionDialog` — confirmation dialog, renders when `selectedUser + pendingAction` set

**Flow**:
1. User types in search → debounced 300ms → `searchValue` updates → `useAdminUsers` re-queries
2. User clicks action → `selectedUser + pendingAction` set → `UserActionDialog` opens
3. Confirm in dialog → `useUserActionMutation(user.id).mutate(action)` called → optimistic row status update → dialog closes
4. API error → dialog shows error, row reverts via `onError`

---

### `SignupPolicyTab` Component Contract

**Responsibilities**: Display and edit signup mode + MFA enforcement.

**State** (managed by React Hook Form):
```typescript
signup_mode: SignupMode
mfa_enforcement: MFAEnforcement
_version: string  // Loaded from query data updated_at
```

**Stale-Data Flow**:
1. Form loads with `defaultValues` from `useSignupPolicy()` data
2. User edits form fields → `isDirty` becomes `true` → Save button enables
3. Submit → `PATCH` with `If-Unmodified-Since: <loaded updated_at>`
4. `412` response → `StaleDataAlert` shown, form stays dirty
5. User clicks "Reload" → `queryClient.invalidateQueries(signupPolicy())` + form reset

**Child Components**:
- `SettingsFormActions` — Save/Reset buttons with `isDirty + isPending + isSaved` props

---

### `QuotasTab` Component Contract

**Two Sections**:
1. **Default Quotas form** — 5 numeric inputs, standard `SettingsFormActions`
2. **Workspace Override section** — combobox workspace selector + 5 nullable numeric inputs

**Workspace Combobox**:
```typescript
// shadcn Command + Popover pattern
selectedWorkspaceId: string | null
// When selectedWorkspaceId changes → useWorkspaceQuota(selectedWorkspaceId) enabled
// Override form resets to loaded data when workspace selection changes
```

---

### `ConnectorsTab` Component Contract

**Responsibilities**: Render list of `ConnectorTypeCard` components, each with autonomous toggle.

**No master Save button** — each toggle auto-saves immediately.

**`ConnectorTypeCard`** internal state:
```typescript
// Optimistic toggle via useConnectorTypeToggleMutation
// AlertTriangle shown when: !config.is_enabled && config.active_instance_count > 0
```

---

### `EmailTab` Component Contract

**Mode toggle**: `smtp | ses` via shadcn `Tabs` (or `RadioGroup`) — switching mode resets form to defaults for that mode.

**Credential masking state** (per credential field):
```typescript
passwordEditMode: boolean  // false = show masked "••••••••", true = show text input
sesKeyEditMode: boolean
```

**"Send Test Email"** inline form:
```typescript
testRecipient: string   // Separate form instance (useForm), does not affect main form dirty state
testResult: { success: boolean; message: string } | null
// useSendTestEmailMutation — 10s timeout, shows spinner on Switch during pending
```

---

### `SecurityTab` Component Contract

Standard settings form pattern — React Hook Form + Zod `securityPolicySchema`.

**Additional**: Informational banner below form explaining "Changes apply only to new authentication events — existing active sessions are not affected."

---

### `StaleDataAlert` Component Contract

```typescript
interface StaleDataAlertProps {
  onReload: () => void;
}
// Renders shadcn Alert with AlertTriangle icon
// "Settings were changed by another administrator. Reload to see the latest values."
// "Reload" button → calls onReload → invalidateQueries + form reset
```

---

### `SettingsFormActions` Component Contract

```typescript
interface SettingsFormActionsProps {
  isDirty: boolean;
  isPending: boolean;
  isSaved: boolean;    // Briefly true after success (1.5s timeout via setTimeout)
  onReset: () => void;
}
// Save button: disabled when !isDirty || isPending
// Button text: isPending → "Saving…" | isSaved → "Saved ✓" | default → "Save"
// Reset button: disabled when !isDirty || isPending, calls form.reset()
```

---

## Route Contract

| Route | Component | Notes |
|-------|-----------|-------|
| `/admin/settings` | Redirect to `/admin/settings?tab=users` | Default tab |
| `/admin/settings?tab=users` | `UsersTab` | P1 |
| `/admin/settings?tab=signup` | `SignupPolicyTab` | P1 |
| `/admin/settings?tab=quotas` | `QuotasTab` | P2 |
| `/admin/settings?tab=connectors` | `ConnectorsTab` | P2 |
| `/admin/settings?tab=email` | `EmailTab` | P3 |
| `/admin/settings?tab=security` | `SecurityTab` | P3 |

**Route Guard**: `apps/web/app/(main)/admin/layout.tsx` — reads `useAuthStore().user.role`, redirects to `/home` + shows 403 toast if not `platform_admin`.
