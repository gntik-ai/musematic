# Functional Requirements — SaaS Transformation Pass

> This document contains the new functional requirements added by the SaaS transformation pass (UPD-046 through UPD-054). It complements `functional-requirements-revised-v6.md` (which covers FR-001 through FR-682). FRs in this document are FR-685 onward, organized into sections 119 through 126.
>
> **Backward-compatibility note**: The `PLATFORM_TENANT_MODE=single|multi` setting (FR-585) is **superseded by this pass**. The platform is always multi-tenant after this pass; the default tenant is created at install time and contains all Free/Pro users. FR-002, FR-030, FR-468, FR-549, FR-585, FR-549 are revised as noted in their respective FRs and in the SaaS constitution.

---

## 119. Tenant Architecture (UPD-046)

### FR-685 Tenant as a First-Class Entity
The platform shall introduce a `Tenant` entity that represents the unit of subdomain-isolated logical separation. Every workspace, user-membership, agent, execution, audit entry, cost record, secret reference, and any other tenant-scoped resource shall carry a `tenant_id` foreign key referencing the `tenants` table. Cross-tenant data access is forbidden except by platform-staff endpoints under `/api/v1/platform/*`.

### FR-686 Tenant Kinds
A tenant has one of two kinds:
- `default` — the SaaS public tenant, exactly one per platform installation, hosting all Free and Pro users. Its slug is `default`, its subdomain is `app`, it cannot be renamed, suspended, or deleted, and a database constraint enforces uniqueness of `kind="default"`.
- `enterprise` — one per contracted Enterprise customer, manually provisioned by super admin. Each enterprise tenant has a unique slug (e.g., `acme`) which becomes its subdomain (`acme.musematic.ai`).

No other kinds exist.

### FR-687 Tenant Schema
The `tenants` table shall contain at minimum: `id` (UUID primary key), `slug` (text, unique, kebab-case, validated regex `^[a-z][a-z0-9-]{1,30}[a-z0-9]$`), `kind` (`default` | `enterprise`), `subdomain` (text, derived from slug or explicitly set), `display_name` (text), `region` (text, references region catalog from FR-468), `data_isolation_mode` (`pool` | `silo`, default `pool`), `branding_config_json` (jsonb, Enterprise-only), `subscription_id` (FK to subscriptions, nullable for default tenant which has per-workspace subscriptions), `status` (`active` | `suspended` | `pending_deletion`), `created_at` (timestamp), `created_by_super_admin_id` (FK to users, nullable for default tenant), `dpa_signed_at` (timestamp), `dpa_version` (text), `contract_metadata_json` (jsonb, Enterprise-only).

### FR-688 Default Tenant Provisioning
On platform install, the seeder shall create the default tenant with `slug="default"`, `subdomain="app"`, `kind="default"`, `display_name="Musematic"`, `region` from `PLATFORM_DEFAULT_REGION` env var. Migration scripts shall backfill `tenant_id="<default-tenant-uuid>"` into all existing rows of tenant-scoped tables, preserving all existing data without loss.

### FR-689 Hostname-to-Tenant Resolution Middleware
The platform shall implement a middleware that runs first in the HTTP request pipeline. The middleware extracts the tenant from the `Host` header by stripping the platform domain (`musematic.ai` or `dev.musematic.ai`) and the optional API/Grafana prefix (`api`, `grafana`). The remainder maps to a tenant slug; the lookup populates the request context with the resolved `Tenant` row. Requests with unrecognized hostnames return HTTP 404 with a generic message that does not reveal whether the tenant exists.

### FR-690 PostgreSQL Row-Level Security on Tenant-Scoped Tables
Every tenant-scoped table shall have a `CREATE POLICY tenant_isolation` RLS policy with the predicate `USING (tenant_id = current_setting('app.tenant_id')::uuid)`. The application middleware shall execute `SET LOCAL app.tenant_id = '<tenant-uuid>'` at the start of every request transaction. RLS is a defense-in-depth backstop; application code must still filter explicitly.

### FR-691 Privileged DB Role for Cross-Tenant Queries
A separate PostgreSQL role `musematic_platform_staff` shall have `BYPASSRLS` privilege. Only platform-staff endpoints (`/api/v1/platform/*`) may use this role, via a dedicated database connection pool. The application database role `musematic_app` does NOT have `BYPASSRLS`.

### FR-692 Subdomain-based Cookie Scoping
Authentication cookies shall be scoped to the tenant's subdomain (`Domain=acme.musematic.ai` for tenant `acme`, `Domain=app.musematic.ai` for default). No cross-subdomain cookie leakage occurs. The default tenant's cookies do NOT have `Domain=.musematic.ai` (which would leak to enterprise tenants).

### FR-693 Per-Tenant OAuth Provider Configuration
Each tenant shall have its own OAuth provider configuration (Google, GitHub) configured by super admin (or by the tenant admin in Enterprise tenants). OAuth callback URLs are tenant-specific (`https://acme.musematic.ai/auth/oauth/google/callback`). The OAuth admin page (UPD-041) operates per-tenant. Default tenant has a platform-managed default OAuth config.

### FR-694 Per-Tenant Vault Path Scoping
Vault paths for tenant-owned resources shall include the tenant slug: `secret/data/musematic/{env}/tenants/{tenant_slug}/{domain}/{resource}`. The default tenant uses paths `secret/data/musematic/{env}/tenants/default/...`. Cross-tenant Vault access is forbidden by Vault policies that grant tenant-scoped read access only.

### FR-695 Tenant Admin Workbench (Super Admin)
The admin workbench (UPD-036) shall include a `/admin/tenants` page operational from this pass forward (no longer feature-flag gated). The page lists all tenants with kind, status, region, subscription state, member count, last-active timestamp. Super admin actions: create new Enterprise tenant (with form: slug, name, region, subscription plan, contract metadata, DPA upload), suspend tenant, delete tenant (with cascade preview and 2PA per FR-561), edit tenant config, switch impersonation context to that tenant.

### FR-696 Tenant Suspension Behavior
A suspended tenant shall: reject all login attempts (returns HTTP 503 with explanatory message), block all background workers from processing tenant-scoped events, retain all data, allow super admin to reactivate at any time. Suspension reasons are logged in audit chain.

### FR-697 Tenant Deletion (Two-Phase)
Deletion is two-phase: phase 1 marks tenant `pending_deletion`, blocks all access, schedules a deletion grace period (default 30 days, configurable per plan); phase 2 (after grace period or super admin force) cascades to all tenant-scoped tables, drops Vault paths, removes OAuth callbacks, removes DNS records (UPD-053), final tombstone audit entry. Until phase 2, super admin can recover the tenant.

### FR-698 Tenant Audit Chain Inclusion
Every audit chain entry shall include `tenant_id` as an additional field. The chain hash includes this field. Cross-tenant audit queries are platform-staff-only.

### FR-699 Tenant Cost Attribution Inclusion
Every cost record (UPD-027) shall include `tenant_id`. Per-tenant cost dashboards (super admin) show platform infrastructure cost vs tenant subscription revenue (gross margin per tenant for platform-staff insight). Per-tenant chargeback to workspaces continues as before.

### FR-700 Tenant Data Residency Enforcement
The `tenant.region` field, combined with FR-468 query-time enforcement, ensures all tenant data lives in the configured region. Cross-region transfers blocked at query level. Super admin sets the region at tenant creation; changing region requires data migration (out of scope this pass — handled as ops procedure).

### FR-701 Per-Tenant Branding (Enterprise Only)
Enterprise tenants shall be able to configure: logo URL, primary color, secondary color, favicon, login page background. These are stored in `tenant.branding_config_json`. Default tenant uses platform-default branding (Musematic logo, neutral colors). Pro/Free workspaces in the default tenant cannot customize branding (constitution rule 14).

### FR-702 Tenant Status Page Subdomain
Each tenant shall have its own status page subdomain when status page is provisioned: `status.acme.musematic.ai` for `acme`, `status.musematic.ai` for default. The status page deployment (UPD-045) is extended to per-tenant routing.

### FR-703 Tenant E2E Test Coverage
A new E2E journey **J22 Tenant Provisioning** shall exercise: super admin creates an Enterprise tenant, super admin assigns plan, super admin invites first tenant admin, tenant admin completes onboarding, tenant admin invites a second user, second user logs in successfully and CANNOT log into another tenant. Cross-tenant isolation verified.

### FR-704 Tenant Listing for Authenticated Users
A user authenticated via SSO/OAuth at one tenant shall NOT see other tenants. The "tenant switcher" UI (if any) only appears for users with explicit memberships across tenants. Listing of available tenants for a user is via `/api/v1/me/memberships` returning only tenants where the user has membership.

### FR-705 Default Tenant Self-Healing Constraints
A migration that would attempt to delete or rename the default tenant shall fail at the database level (CHECK constraint or trigger). The default tenant is hardcoded by slug `default` and kind `default`; admin UI prevents deletion attempts and explains why.

---

## 120. Plans, Subscriptions, Quotas (UPD-047)

### FR-706 Plans Table with Configurable Parameters
The `plans` table shall contain at minimum: `id` (UUID), `slug` (text, e.g., `free`, `pro`, `enterprise`), `display_name`, `description`, `tier` (`free` | `pro` | `enterprise`), `is_public` (boolean — Enterprise is `false`, doesn't appear in public pricing), `is_active` (boolean), `allowed_model_tier` (text — e.g., `cheap_only` for Free), `created_at`. Plans have versions (separate `plan_versions` table) holding the configurable parameters.

### FR-707 Plan Version Configurable Parameters
Each `plan_versions` row shall contain super-admin-configurable parameters:
- `version` (integer, monotonic per plan)
- `price_monthly` (decimal, in EUR, 0 = no overage allowed for any quota of this plan)
- `executions_per_day` (integer, 0 = unlimited)
- `executions_per_month` (integer, 0 = unlimited)
- `minutes_per_day` (integer, 0 = unlimited)
- `minutes_per_month` (integer, 0 = unlimited)
- `max_workspaces` (integer, 0 = unlimited)
- `max_agents_per_workspace` (integer, 0 = unlimited; counts only agents with at least one active revision per FR-674)
- `max_users_per_workspace` (integer, 0 = unlimited)
- `overage_price_per_minute` (decimal, 0 = no overage allowed)
- `trial_days` (integer, default 0)
- `published_at` (timestamp, null until published)
- `deprecated_at` (timestamp, null while accepting new subscriptions)

A value of 0 for any quota parameter means **unlimited** per user requirement.

### FR-708 Plan Version Immutability
Once a plan version is `published_at`, it MUST NOT be modified. Editing parameters creates a new plan version (auto-increment `version`). Existing subscriptions remain pinned to their plan version. The admin UI shows version history with diffs.

### FR-709 Subscription Schema
The `subscriptions` table shall contain at minimum: `id` (UUID), `tenant_id` (FK), `scope_type` (`workspace` | `tenant`), `scope_id` (UUID — the workspace or tenant being subscribed), `plan_id` (FK), `plan_version` (integer), `status` (`trial` | `active` | `past_due` | `cancellation_pending` | `canceled` | `suspended`), `started_at`, `current_period_start`, `current_period_end`, `cancel_at_period_end` (boolean), `payment_method_id` (FK to payment_methods, nullable for Free), `stripe_subscription_id` (text, nullable for Free), `created_by_user_id` (FK), `created_at`. Constraint: subscriptions in default tenant have `scope_type='workspace'`; subscriptions in enterprise tenants have `scope_type='tenant'`.

### FR-710 Three Free Plans by Default
On platform install, three plans are seeded:
- `free` plan: tier `free`, price 0, executions_per_day 50, executions_per_month 100, minutes_per_day 30, minutes_per_month 100, max_workspaces 1, max_agents_per_workspace 5, max_users_per_workspace 3, overage_price_per_minute 0 (NO overage), allowed_model_tier `cheap_only`, trial_days 0
- `pro` plan: tier `pro`, price 49 EUR, executions_per_day 500, executions_per_month 5000, minutes_per_day 240, minutes_per_month 2400, max_workspaces 5, max_agents_per_workspace 50, max_users_per_workspace 25, overage_price_per_minute 0.10 EUR, allowed_model_tier `all`, trial_days 14
- `enterprise` plan: tier `enterprise`, price 0 (negotiated per contract), all quotas 0 (unlimited), overage 0 (no overage by default — contract custom), allowed_model_tier `all`, trial_days 0, `is_public=false`

These defaults are super-admin-editable; on plan parameter change, a new version is created.

### FR-711 Quota Enforcement Synchronous Check
Before launching an execution, creating a workspace, registering an agent, inviting a user: the platform shall execute synchronous quota check against the workspace's (or tenant's, for Enterprise) subscription's plan version. If exceeded, the operation is rejected with HTTP 402 (for billable resources) or HTTP 403 (for capacity quotas like max_workspaces). Free plan ALWAYS hard-caps; Pro plan triggers the overage authorization flow if `overage_price_per_minute > 0`.

### FR-712 Active Compute Time Counting
The "minutes" quota counts active compute time only: from the moment an agent runtime pod begins processing a step to the moment it releases the slot. Excluded: queue wait time, sandbox provisioning, approval gate waits, attention request waits, idle time. Implementation: the runtime emits `execution.compute.start` and `execution.compute.end` events; a metering service aggregates these per (tenant_id, workspace_id, billing_period).

### FR-713 Hard Cap Enforcement (Free Tier)
A workspace on a Free plan whose execution-minute or execution-count quota is exhausted shall: reject new execution requests with HTTP 402 + body `{"error":"quota_exceeded","quota":"minutes_per_month","reset_at":"<timestamp>","upgrade_url":"/upgrade"}`. UI shows a clear "Upgrade to Pro" CTA. No grace period. No overage option.

### FR-714 Overage Authorization (Pro Tier with Overage Enabled)
A workspace on a Pro plan with `overage_price_per_minute > 0` whose quota is exhausted shall: pause execution with status `paused_quota_exceeded`, send notification to workspace admin via UPD-042 notification center channel(s) with subject "Authorize overage for this period", body explaining estimated overage cost based on recent burn rate, button to authorize. Authorization records `overage_authorizations` row with `(workspace_id, billing_period_start, authorized_at, authorized_by_user_id, max_overage_eur)` — defaulting to "unlimited until period end" or capped at user-set value. After authorization, paused executions resume.

### FR-715 Overage Pricing Configuration
The `overage_price_per_minute` from the plan version applies. When 0, overage is unavailable (hard cap regardless of card on file). Per-tenant Enterprise contracts can override via custom contract metadata (out of scope auto-enforcement; super admin tracks).

### FR-716 Quota Reset Periods
Daily quotas reset at midnight in the tenant's region timezone (configurable). Monthly quotas reset on the 1st of the month at the same boundary OR on subscription anniversary date — choice configurable per plan via `quota_period_anchor` ∈ {`calendar_month`, `subscription_anniversary`}. Default: `calendar_month` for Free, `subscription_anniversary` for Pro/Enterprise.

### FR-717 Plan Upgrade and Downgrade
A workspace can upgrade plans at any time. Upgrade takes effect immediately with prorated billing (Stripe handles proration). The plan version of the upgrade is the current published version of the new plan. Downgrade scheduled for next period boundary by default (data exceeding new plan limits triggers cleanup notification per FR-742). Super admin can override downgrade timing per plan.

### FR-718 Plan Configuration Admin UI
Super admin shall have a `/admin/plans` page listing all plans with current published version. Per-plan: edit (creates new version, requires "Publish" action), view version history, mark version deprecated (no new subscriptions on that version), see active subscription count per version.

### FR-719 Plan Version History
The `/admin/plans/{plan_id}/history` page shall show all versions with diffs (parameter-by-parameter), publication timestamps, and deprecation status. Each version shows count of subscriptions still on it.

### FR-720 Subscription Admin Dashboard
Super admin shall have `/admin/subscriptions` listing all subscriptions across tenants. Filters: tenant, plan, status, payment status. Drill into subscription detail with: status timeline, payment history, current period usage, plan version, upgrade/downgrade history.

### FR-721 Subscription Status Transitions
Allowed status transitions:
- `trial` → `active` (after first successful payment or trial conversion)
- `trial` → `canceled` (user abandons trial)
- `active` → `past_due` (payment failure, FR-739)
- `past_due` → `active` (payment recovers)
- `past_due` → `suspended` (after retry exhaustion + grace period)
- `suspended` → `active` (manual super admin action)
- `*` → `cancellation_pending` (user requests cancellation, takes effect at period end)
- `cancellation_pending` → `canceled` (period ends)

Other transitions are illegal and rejected.

### FR-722 Plans, Subscriptions, Quotas E2E Coverage
A new E2E journey **J23 Quota Enforcement** shall exercise: Free workspace hits hard cap, Pro workspace triggers overage flow with authorization, Enterprise tenant ignores caps, plan upgrade applies new quotas immediately, plan downgrade scheduled for period end. Cross-checks with cost attribution dashboard (UPD-027) and notification center (UPD-042).

---

## 121. Public Signup, Default Tenant Only (UPD-048)

### FR-723 Public Signup Restricted to Default Tenant
The public signup page (UPD-037 `/signup`) shall be available only at `app.musematic.ai/signup` (the default tenant subdomain). Visiting `https://acme.musematic.ai/signup` returns 404 (Enterprise tenants do not allow public signup). Enterprise tenants invite users via tenant admin only.

### FR-724 Signup Creates User in Default Tenant Only
Public signup creates a user with `tenant_id=<default-tenant-uuid>`. No tenant is created at signup time. The user lands in the default tenant and proceeds with workspace creation in default tenant context.

### FR-725 Free Workspace Auto-Creation on First Signup
On a user's first signup confirmation (after email verification, after any required admin approval per FR-016 — though the default tenant typically has approval disabled), a Free-plan workspace is automatically created with the user as `workspace_owner`. The user lands on the workspace dashboard.

### FR-726 Onboarding Wizard
After workspace auto-creation, an onboarding wizard guides the user through: name your workspace, optionally invite teammates (via UPD-042 invite flow), create your first agent (link to creation wizard from UPD-022), or skip and explore. Wizard is dismissible.

### FR-727 Enterprise Tenant User Provisioning
Enterprise tenants are provisioned by super admin via `/admin/tenants/new`. The form collects: tenant slug, display name, region, plan (Enterprise plan version), contract metadata (DPA file upload, contract reference), first tenant admin email. On submit: tenant row created, DNS record created (UPD-053), TLS cert provisioned (Let's Encrypt automation), first tenant admin invited via email, audit chain entry recorded with super admin principal.

### FR-728 Tenant Admin Onboarding Flow
The first tenant admin of an Enterprise tenant receives an invitation email with link to `https://acme.musematic.ai/setup`. The setup flow: accept terms, create password (or link OAuth), set up MFA (mandatory for tenant admins), create first workspace, invite teammates, configure tenant SSO (optional). After completion, tenant is `active`.

### FR-729 Per-Tenant Branding Visible at Signup/Login
At `acme.musematic.ai/login`, the tenant's branding (logo, colors per FR-701) is applied to the login page. At `app.musematic.ai/login`, default Musematic branding is applied.

### FR-730 Default Tenant User Cannot Login at Enterprise Subdomain
A user registered in default tenant attempting to log in at `acme.musematic.ai/login` is rejected with HTTP 401 + message "This account is not associated with this organization. Did you mean to log in at app.musematic.ai?". No information leakage about whether the email exists in any tenant.

### FR-731 Cross-Tenant User Memberships
A user CAN have memberships in multiple tenants if explicitly invited. Each membership is a separate row in `user_memberships` with `(user_id, tenant_id, default_workspace_id, created_at)`. The user logs in at the appropriate subdomain for each tenant. SSO/OAuth providers are tenant-scoped (FR-693), so the SSO at `acme` may differ from the SSO at default; the same user may use email+password in default and OIDC in `acme`.

### FR-732 Public Signup E2E Coverage
Extend J19 (UPD-037 New User Signup) to verify: signup at `app.musematic.ai/signup` succeeds, signup at `acme.musematic.ai/signup` returns 404, free workspace auto-created, user redirected to onboarding wizard. New journey **J24 Enterprise Tenant Provisioning** covers super admin manual tenant creation flow.

---

## 122. Marketplace Scope (UPD-049)

### FR-733 Marketplace Scopes
Agents and shared resources have a `marketplace_scope` field with allowed values:
- `workspace` — visible only within the publishing workspace
- `tenant` — visible to all workspaces within the publishing tenant
- `public_default_tenant` — visible to all users of the default tenant (free/pro public marketplace, Anthropic-style hub)

Enterprise tenants cannot publish to `public_default_tenant`. Free/Pro workspaces in default tenant can publish to any of the three scopes.

### FR-734 Public Marketplace Visibility
Resources with `marketplace_scope=public_default_tenant` are visible to all users of the default tenant. They appear in the marketplace search and discovery (FR-234 et seq) for users in default tenant.

### FR-735 Enterprise Tenant Consumption of Public Marketplace (Per-Contract Flag)
By default, Enterprise tenants do NOT see public marketplace resources. Super admin can enable `tenant.feature_flags.consume_public_marketplace=true` per Enterprise tenant (per-contract). When enabled, Enterprise users can browse and use (read-only) resources from the public default-tenant marketplace, but cannot publish to it.

### FR-736 Marketplace Publication Review (Public Scope Only)
Publishing to `public_default_tenant` requires platform-staff review (similar to app store submissions). The publication state machine: `draft` → `pending_review` (user submits) → `approved` | `rejected` (platform staff decision) → `published` (after approval) → `deprecated`. Reviewers verify: agent doesn't violate ToS, agent is not a security risk, agent doesn't impersonate other entities, agent description is accurate.

### FR-737 Marketplace Submission UI
The creator workbench shall include a marketplace submission flow at `/agent-management/{fqn}/publish` allowing the user to choose `marketplace_scope`. Scopes `workspace` and `tenant` publish immediately. Scope `public_default_tenant` requires submission with description, category, tags, and goes to platform-staff review queue.

### FR-738 Marketplace Review Admin UI
Super admin shall have `/admin/marketplace-review` page listing pending submissions with filters by category, submitter tenant, submission age. Per submission: review the agent (test runs in sandbox), see submitter trust history, approve / reject with reason, communicate decision back to submitter via notification.

### FR-739 Marketplace Discovery Per Scope
The marketplace UI (FR-234) shall scope discovery according to the user's tenant context:
- Default tenant user: sees workspace-scope from their workspace, tenant-scope from default tenant, public-scope (visible to all default tenant)
- Enterprise tenant user: sees workspace-scope from their workspace, tenant-scope from their tenant, plus public-scope if `consume_public_marketplace` enabled for their tenant

### FR-740 Agent Cross-Tenant Read Access
When an Enterprise tenant consumes a public marketplace agent, the agent is loaded read-only with metadata clearly indicating "from public marketplace, not editable". Execution proceeds in the consuming tenant's runtime; cost attribution to consuming tenant. Forking the agent into the consuming tenant's workspace is allowed; the fork becomes a regular `tenant` or `workspace` scoped agent in the new home.

### FR-741 Marketplace Scope E2E Coverage
A new E2E journey **J25 Marketplace Multi-Scope** shall exercise: default-tenant user publishes agent to public scope, super admin reviews and approves, second default-tenant user discovers and runs the agent, Enterprise tenant with `consume_public_marketplace=true` discovers and runs (read-only), Enterprise tenant without flag does NOT see the agent. Cross-tenant isolation for tenant-scope agents verified.

---

## 123. Abuse Prevention and Trust & Safety (UPD-050)

### FR-742 Free Tier Cost Protection (Hard)
The Free plan shall be economically protected via:
- Allowed model tier `cheap_only` (FR-707): no GPT-4, no Claude Opus, no premium models
- Hard caps with no overage option
- Maximum execution time per run (default 5 minutes wall-clock)
- Maximum reasoning depth (default 3 layers)
- Maximum context size (default 8192 tokens)

These limits are configurable in the plan version parameters (extension to FR-707) and enforced at runtime.

### FR-743 Disposable Email Domain Detection
Public signup at `app.musematic.ai/signup` shall reject emails from a maintained disposable-email-provider list (default list embedded; updateable via cron from a public source like `disposable-email-domains` GitHub project). Rejected with HTTP 400 + message "Please use a non-disposable email address". Super admin can override per email if needed.

### FR-744 Velocity Rules on Signup
The platform shall track signup velocity per IP, ASN, and email domain. Default thresholds:
- 5 signups per IP per hour (HTTP 429)
- 50 signups per ASN per hour (HTTP 429)
- 20 signups per email domain per day (warning notification to super admin)

Thresholds configurable in `/admin/security/abuse-prevention`.

### FR-745 CAPTCHA on Signup (Configurable)
Optional CAPTCHA (hCaptcha or Cloudflare Turnstile, configurable) on signup. Activatable by super admin. When activated, signup form requires successful CAPTCHA solve. Default: disabled until abuse spike detected; super admin can auto-enable via abuse-prevention page.

### FR-746 Account Suspension Automation
The platform shall support automated suspension of free-tier users matching abuse patterns:
- Multiple Free workspaces from same IP within short window
- Cost burn rate exceeding thresholds (despite hard cap)
- Reported abuse by other users
- Failed payment attempts from card stuffing patterns

Suspended users see "Account suspended pending review" with appeal contact. Super admin reviews queue at `/admin/security/suspensions`.

### FR-747 Per-IP Geo-Blocking (Optional)
Super admin can configure geo-blocking lists at `/admin/security/geo-policy`: allow-list mode (only specified countries) or block-list mode (block specified countries). Useful for blocking high-abuse regions. Defaults: empty (no geo restriction). Geolocation via MaxMind GeoLite2 (open source) or paid GeoIP2.

### FR-748 ML-Based Fraud Scoring (Optional Integration)
The platform shall support optional integration with external fraud-scoring services (MaxMind minFraud, Sift). When enabled (super admin at `/admin/security/fraud-scoring`), signups receive a fraud score; high-score signups are auto-suspended pending review. Disabled by default; opt-in.

### FR-749 Abuse Prevention Admin UI
Super admin shall have `/admin/security/abuse-prevention` showing: signup velocity dashboards, suspension queue, CAPTCHA status, geo-block config, fraud scoring config, recent abuse incidents. Actions: suspend user, lift suspension, ban IP, ban email domain, force CAPTCHA enable, edit thresholds.

### FR-750 Abuse Prevention E2E Coverage
A new E2E journey **J26 Abuse Prevention** shall exercise: bot creating 10 signups from same IP triggers velocity block, disposable email rejected, suspended account login blocked with appropriate message, super admin lifts suspension, suspended user can re-login.

---

## 124. Data Lifecycle (Tenant and Workspace) (UPD-051)

### FR-751 Workspace Data Export (Free/Pro)
A workspace owner or admin (default tenant) shall be able to export their workspace data via `/workspaces/{id}/data-export`. Export includes: agents, revisions, executions, audit log, conversations, costs, members. Format: ZIP with structured JSON files + raw artifacts. Email notification on completion with download link valid 7 days. Implementation: async background job, atomic.

### FR-752 Workspace Deletion (Free/Pro)
Workspace owner can request deletion at `/workspaces/{id}/settings` with typed confirmation. Two-phase: phase 1 marks `pending_deletion` and emails owner with 7-day cancel link; phase 2 (after 7 days) cascades deletion of all workspace-scoped resources. Tombstone audit entry retained 90 days then purged.

### FR-753 Tenant Data Export (Enterprise)
A tenant admin (or super admin) of an Enterprise tenant shall be able to export the entire tenant data via `/admin/tenants/{id}/data-export`. Same format as workspace export but tenant-scoped. Useful for contractual data egress at contract end.

### FR-754 Tenant Deletion Cascade (Enterprise)
Per FR-697, Enterprise tenant deletion is two-phase. Cascade includes: all workspaces, all agents, all executions, all audit (final tombstone export to S3 retained per regulatory requirements separately), all secrets in Vault paths, all DNS records, all TLS certs revoked, all subscription records.

### FR-755 Data Processing Agreement (DPA) per Tenant
Every tenant shall have a DPA on file. Default tenant: standard DPA shown clickwrap-style at signup, version pinned per user signup. Enterprise tenant: custom DPA uploaded by super admin at tenant creation, signed by both parties out-of-band, file hash stored.

### FR-756 Sub-Processors Public List
The platform shall publish a public sub-processors list at `https://musematic.ai/legal/sub-processors` listing all third-party services that process customer data: Anthropic (LLM), OpenAI (LLM), Hetzner (infrastructure), Stripe (billing), SendGrid or Postmark (email), MaxMind (fraud, if enabled). Updated at least quarterly. Customers notified via email on changes (subscribe-only via DPA).

### FR-757 Tenant Suspension Data Retention
A suspended tenant's data is retained but inaccessible. After 90 days suspended (configurable), super admin can: reactivate, force-delete, or extend suspension. Default policy: 90 days suspension + 30 days deletion grace = 120 days total before purge.

### FR-758 GDPR Article 28 Compliance for Enterprise
Enterprise contracts include GDPR Article 28 controller-processor terms. Super admin manages compliance evidence (DPA, sub-processors, technical & organizational measures documentation) via `/admin/legal/gdpr` page.

### FR-759 Backup Separation by Tenant
Backups (UPD-024 + UPD-025) shall be tenant-aware: deleted tenants' data is purged from backups within 30 days (regulatory deletion timeline). Backup index includes `tenant_id` for selective restore.

### FR-760 Data Lifecycle E2E Coverage
A new E2E journey **J27 Tenant Lifecycle Cancellation** shall exercise: Enterprise tenant requests cancellation, super admin initiates deletion phase 1, tenant data export downloaded, 30-day grace passes, phase 2 cascade executes, DNS removed, all data verified purged. Workspace deletion path covered as part of J20 extension.

---

## 125. Billing and Overage (UPD-052)

### FR-761 PaymentProvider Abstraction
The platform shall implement a `PaymentProvider` interface (Python and Go) abstracting payment operations: `create_customer`, `attach_payment_method`, `create_subscription`, `update_subscription`, `cancel_subscription`, `report_usage`, `charge_overage`, `handle_webhook`. Concrete implementations live at `apps/control-plane/src/platform/billing/providers/`. Stripe is the first impl.

### FR-762 Stripe as First Concrete Implementation
The Stripe `PaymentProvider` shall use Stripe's Subscriptions API for fixed-price plans, Stripe's Usage Records for metered overage, Stripe Tax for IVA OSS handling (Spanish entity selling to EU), Stripe Customer Portal for self-service subscription management. SDK: `stripe-python` and `stripe-go`.

### FR-763 Stripe Webhooks at `/api/webhooks/stripe`
The platform shall expose `POST /api/webhooks/stripe` (single endpoint, NOT tenant-scoped by hostname — Stripe sends to one URL). Handler verifies HMAC signature using Stripe webhook secret, parses event, resolves tenant via Stripe customer ID lookup, dispatches to appropriate handler. Idempotency: Stripe event ID stored in `processed_webhooks` table, duplicate events return 200 immediately.

### FR-764 Webhook Event Handlers
At minimum, the platform handles these Stripe events:
- `customer.subscription.created` — sync subscription state
- `customer.subscription.updated` — sync state changes
- `customer.subscription.deleted` — handle cancellation
- `invoice.payment_succeeded` — extend subscription period
- `invoice.payment_failed` — start grace period (FR-768)
- `customer.subscription.trial_will_end` — notify user 3 days before
- `payment_method.attached` — register payment method
- `charge.dispute.created` — auto-suspend, alert super admin

### FR-765 Free Plan Card-on-File Allowed
Per user requirement (a), Free workspaces CAN have a card on file. The card enables: future upgrade to Pro without re-entering card, optional overage if user upgrades and overage applies. Card on file does NOT enable overage on Free (constitution rule 25).

### FR-766 Overage Authorization UX
Per FR-714: when Pro workspace hits 100% quota with `overage_price_per_minute > 0`, executions pause. Notification with action button "Authorize overage for this period" (UX option C). Authorization records `overage_authorizations` row. Authorization is per-period; new period requires new authorization.

### FR-767 Overage Authorization with Optional Cap
The authorization UI lets the user set: "Authorize unlimited overage for the period" or "Authorize up to N euros of overage". Once cap reached, executions pause again with notification.

### FR-768 Failed Payment Grace Period
Per user requirement (b): when a Pro subscription's payment fails (Stripe `invoice.payment_failed`), the platform initiates 7-day grace period. During grace: workspace continues operating with subscription status `past_due`, daily reminder emails sent (3 reminders over 7 days), Stripe Smart Retries attempt re-charge. On day 7 if still failed: subscription status `suspended`, workspace downgraded to Free plan with notification, data exceeding Free limits triggers cleanup notification per FR-742.

### FR-769 Subscription Cancellation Flow
User can cancel subscription at `/workspaces/{id}/billing/cancel`. Cancellation effective at period end by default (status `cancellation_pending`). Optional immediate cancellation with prorated refund (super admin policy). On cancellation, workspace downgrades to Free at period end. Cancellation reasons collected for retention analysis.

### FR-770 Stripe Customer Portal Integration
For self-service subscription management (update card, view invoices, cancel), the platform shall embed or link Stripe Customer Portal at `/workspaces/{id}/billing/portal`. Portal session created server-side with workspace's Stripe customer ID. Portal returns user to platform after actions; webhooks sync state.

### FR-771 Invoices and Receipts
Invoices generated by Stripe (auto-emailed to billing email). Platform shall provide a `/workspaces/{id}/billing/invoices` page listing invoices with download links to Stripe-hosted PDFs. Tenant admin (Enterprise) sees tenant-level invoices.

### FR-772 Billing Dashboard Per Workspace (Pro/Free)
A workspace owner shall have `/workspaces/{id}/billing` showing: current plan, current period usage (executions, minutes) with progress bars vs quota, projected end-of-period usage and overage estimate, payment method, recent invoices, upgrade/downgrade actions, cancel subscription action.

### FR-773 Billing Dashboard Per Tenant (Enterprise)
Enterprise tenant admin shall have `/admin/tenants/{id}/billing` showing tenant-level subscription state, invoices, contract status. Cost rollup across all tenant workspaces.

### FR-774 Stripe Test Mode for Dev Environment
Per constitution rule "Dev cluster isolation is real": dev environment uses Stripe test mode. Production uses Stripe live mode. Configuration via `PLATFORM_STRIPE_MODE=test|live` env var. Test cards (Stripe documented) usable in dev.

### FR-775 Billing E2E Coverage
A new E2E journey **J28 Billing Lifecycle** shall exercise: workspace upgrade Free→Pro with card, successful first payment, hit overage threshold and authorize, payment failure triggers grace period, payment recovery, payment failure exhausts grace and downgrades, subscription cancellation, period-end downgrade, refund flow.

---

## 126. Hetzner Production+Dev Helm and Ingress Topology (UPD-053)

### FR-776 Two Separate Kubernetes Clusters
The production deployment topology shall consist of two physically separated Hetzner Cloud Kubernetes clusters: `musematic-prod` and `musematic-dev`. Each cluster is provisioned independently via Terraform, has its own kubeconfig, and runs its own platform Helm release.

### FR-777 Cluster Sizing Profiles
Production cluster default: 1 control plane (CCX33) + 3 worker nodes (CCX53), Hetzner network zone `eu-central`, dedicated Cloud Load Balancer (`lb21` size).
Dev cluster default: 1 control plane (CCX21) + 1 worker node (CCX21), same network zone, smaller LB (`lb11` size).
Both sizes documented in Terraform variables, super admin overridable.

### FR-778 Hetzner Cloud Load Balancer per Cluster
Each cluster shall have a dedicated Hetzner Cloud Load Balancer fronting its NGINX Ingress Controller. LB annotations on the ingress-nginx Service:
- `load-balancer.hetzner.cloud/location: nbg1`
- `load-balancer.hetzner.cloud/network-zone: eu-central`
- `load-balancer.hetzner.cloud/use-private-ip: "true"`
- `load-balancer.hetzner.cloud/uses-proxyprotocol: "true"` (optional, for source IP preservation)
- `load-balancer.hetzner.cloud/name: musematic-prod-lb` / `musematic-dev-lb`

LB exposes ports 80 (redirect to 443) and 443.

### FR-779 DNS Topology
Production DNS at Hetzner DNS (or Cloudflare DNS, super admin choice):
- `musematic.ai` → A/AAAA → prod LB IPs (apex, redirects to `app.musematic.ai`)
- `app.musematic.ai` → CNAME → `musematic.ai` (or A/AAAA)
- `api.musematic.ai` → A/AAAA → prod LB IPs
- `grafana.musematic.ai` → A/AAAA → prod LB IPs
- `*.musematic.ai` → wildcard A/AAAA → prod LB IPs (covers Enterprise tenant subdomains)
- `dev.musematic.ai` → A/AAAA → dev LB IPs
- `*.dev.musematic.ai` → wildcard A/AAAA → dev LB IPs
- `api.dev.musematic.ai` → CNAME → `dev.musematic.ai` (also `dev.api.musematic.ai` per spec)
- `dev.api.musematic.ai` → A/AAAA → dev LB IPs
- `dev.grafana.musematic.ai` → A/AAAA → dev LB IPs

CAA record:
- `musematic.ai` → CAA `0 issue "letsencrypt.org"`

### FR-780 Wildcard TLS per Environment
Production wildcard cert: `*.musematic.ai` (covers `app`, `api`, `grafana`, `acme`, `acme.api`, `acme.grafana`, etc.). Dev wildcard cert: `*.dev.musematic.ai`. Issued via cert-manager + Let's Encrypt DNS-01 challenge against Hetzner DNS API. Renewal automated 30 days before expiry.

### FR-781 cert-manager + Let's Encrypt DNS-01 Configuration
The Helm chart shall ship cert-manager configuration including:
- ClusterIssuer `letsencrypt-prod` (production) and `letsencrypt-staging` (testing)
- DNS-01 solver using Hetzner DNS via webhook (e.g., `cert-manager-webhook-hetzner` from community)
- API token stored in Vault (UPD-040) at `secret/data/musematic/{env}/cert-manager/hetzner-dns-token`
- Two Certificate resources per environment: wildcard `*.musematic.ai` and apex `musematic.ai` (for prod), `*.dev.musematic.ai` and `dev.musematic.ai` (for dev)

### FR-782 Per-Tenant Ingress Routing
Production ingress shall route by Host header:
- Apex `musematic.ai` → frontend pod (or 301 redirect to `app.musematic.ai`)
- `app.musematic.ai` → frontend pod with default tenant context
- `api.musematic.ai` → control plane API pod
- `grafana.musematic.ai` → Grafana service (with admin SSO gate)
- `*.musematic.ai` (any subdomain matching tenant slug pattern) → frontend pod with subdomain extracted
- `*.api.musematic.ai` → control plane API pod with subdomain extracted
- `*.grafana.musematic.ai` → Grafana with tenant-scoped dashboard set
- `status.musematic.ai` and `*.status.musematic.ai` → status page service (independent pod)

Dev environment mirrors with `dev.` prefix per FR-779.

### FR-783 Helm Chart Overlay Structure
The platform Helm chart shall ship with three values overlays:
- `values.yaml` — sensible defaults
- `values-prod.yaml` — production overrides (full sizing, HA, real Stripe, prod DNS, prod Vault HA)
- `values-dev.yaml` — dev overrides (smaller sizing, single replicas, Stripe test mode, dev DNS, dev Vault standalone)

Each overlay is checked into `deploy/helm/platform/` and version-controlled.

### FR-784 Helm Chart Manages Tenant Subdomains via Wildcard Ingress
The wildcard ingress (`*.musematic.ai`) is configured at install time. New Enterprise tenants need NO ingress changes — the wildcard catches them automatically. Only DNS automation (FR-786) is needed when adding a tenant.

### FR-785 Per-Environment Stripe Webhook Endpoints
Production Stripe webhook: `https://api.musematic.ai/api/webhooks/stripe` configured in Stripe live mode. Dev Stripe webhook: `https://dev.api.musematic.ai/api/webhooks/stripe` configured in Stripe test mode. Webhook secrets stored in Vault under `secret/data/musematic/{env}/billing/stripe-webhook-secret`.

### FR-786 Tenant Subdomain DNS Automation
On Enterprise tenant creation, the platform shall automate DNS record creation via Hetzner DNS API (or Cloudflare DNS API, configured per `PLATFORM_DNS_PROVIDER`). The automation creates: A/AAAA for `<slug>.musematic.ai`, A/AAAA for `<slug>.api.musematic.ai`, A/AAAA for `<slug>.grafana.musematic.ai`. On tenant deletion (phase 2), records are removed.

### FR-787 Hetzner DNS Provider API Token
The Hetzner DNS API token is stored in Vault at `secret/data/musematic/{env}/dns/hetzner-token`. The token has scope: write to `musematic.ai` zone only. Token rotation per UPD-024 secret rotation procedure.

### FR-788 Status Page Cluster Independence
Per UPD-045 constitution rule 49: status page shall NOT live in the same cluster as the platform. Hosted on either: (a) Cloudflare Pages with static generation, or (b) a tiny dedicated Hetzner VM with nginx serving static files. CronJob in production cluster polls health and pushes regenerated content to the independent host.

### FR-789 Helm Values for Hetzner-Specific Configuration
The Helm chart shall expose Hetzner-specific values:
```yaml
hetzner:
  loadBalancer:
    location: nbg1
    networkZone: eu-central
    usePrivateIp: true
    proxyProtocol: true
    name: musematic-prod-lb  # or musematic-dev-lb
  dns:
    provider: hetzner  # or cloudflare
    apiTokenSecretRef:
      name: hetzner-dns-token
      key: token
    zone: musematic.ai
```

### FR-790 Helm Chart Test Coverage
Helm chart shall be tested via:
- `helm lint` in CI
- `helm template` snapshot tests against expected output
- `helm install --dry-run` against a kind cluster
- Full deployment test on dev cluster as part of CI promotion gate

### FR-791 Hetzner Topology E2E Coverage
A new E2E journey **J29 Hetzner Topology** shall exercise (in dev cluster): platform install via Helm, DNS records visible, TLS certs issued, default tenant accessible at `app.dev.musematic.ai`, Enterprise tenant creation triggers DNS automation, new tenant subdomain accessible within 5 minutes, tenant deletion removes DNS, no leaked subdomains.

---

## 127. SaaS Comprehensive E2E (UPD-054)

### FR-792 J22 Tenant Provisioning Journey
Already specified in FR-703. Comprehensive coverage: super admin creates tenant, DPA upload, tenant subdomain DNS appears, TLS issues, first admin invite, login at tenant subdomain, cross-tenant isolation verified.

### FR-793 J23 Quota Enforcement Journey
Already specified in FR-722. Free hard cap, Pro overage authorization flow, Enterprise unlimited verification.

### FR-794 J24 Enterprise Tenant Provisioning Journey
Already specified in FR-732. Manual creation flow with DNS, TLS, branding, SSO config.

### FR-795 J25 Marketplace Multi-Scope Journey
Already specified in FR-741. Public marketplace with review, Enterprise consume flag, cross-tenant isolation.

### FR-796 J26 Abuse Prevention Journey
Already specified in FR-750. Bot detection, disposable email, suspension flow.

### FR-797 J27 Tenant Lifecycle Cancellation Journey
Already specified in FR-760. Cancellation, deletion grace, data export, cascade purge.

### FR-798 J28 Billing Lifecycle Journey
Already specified in FR-775. Upgrade, payment, overage, grace period, downgrade, cancellation.

### FR-799 J29 Hetzner Topology Journey
Already specified in FR-791. DNS automation, TLS, tenant subdomain provisioning.

### FR-800 J30 Plan Versioning Journey
Super admin edits Pro plan parameters → new plan version published. Existing Pro subscriptions remain on old version. New signups land on new version. Existing Pro user can opt-in upgrade to new version with prorated billing. Plan history page shows diffs. Constraint: editing already-published version is rejected.

### FR-801 J31 Cross-Tenant Isolation Verification Journey
Comprehensive negative test: User A in default tenant, User B in tenant Acme. Verify: A cannot read B's workspaces, agents, executions, audit, costs, secrets. B cannot read A's data. Direct API attempts with crafted requests return 404 (no information leak about whether resource exists). RLS enforced via positive test (privileged platform-staff role can see both, regular role sees only their tenant).

### FR-802 J32 Stripe Webhook Idempotency Journey
Send duplicate webhook events from Stripe (test mode replay). Verify: first event processed; second event short-circuits with HTTP 200 idempotent response; `processed_webhooks` table prevents reprocessing. Verify subscription state correct (no double-extension of period).

### FR-803 J33 Trial-to-Paid Conversion Journey
User signs up Pro with 14-day trial. Verify: status `trial`, no payment yet, full Pro features. On day 11 receives `trial_will_end` notification. On day 14 trial ends, Stripe charges card, status transitions to `active`. If card fails, status `past_due` and grace begins.

### FR-804 J34 Subscription Cancellation and Reactivation Journey
Pro user cancels subscription. Status → `cancellation_pending`. User retains Pro until period end. User changes mind before period end → reactivates → status → `active`. After period end without reactivation: `canceled`, downgraded to Free.

### FR-805 J35 Wildcard TLS Renewal Journey
Force a near-expiry simulation (set cert ttl low in dev). Verify: cert-manager auto-renews 30 days before expiry. Verify: no service interruption during renewal. Verify: alert fires if renewal fails.

### FR-806 J36 Default Tenant Constraint Journey
Attempt various forbidden operations on default tenant: delete via API → blocked with HTTP 403. Suspend via API → blocked. Rename via API → blocked. Migration that would drop or alter the default tenant row fails at constraint check. Default tenant always exists in healthy state.

### FR-807 J37 Plan Free Cost Protection Journey
Free user attempts to use premium model (e.g., GPT-4) → execution rejected with quota_exceeded for premium model tier. Free user attempts large context window → rejected. Free user runs many small executions until quota exhausted → hard cap with HTTP 402. Verify zero overage cost incurred.

### FR-808 SaaS E2E Suite Completion Criterion
The SaaS pass is complete when J22 through J37 (16 new journeys) all pass against a deployed dev cluster, plus regression of J01 through J21 (21 prior journeys, post-tenant-refactor). Total: 37 journeys × ~30 assertion points = ~1100+ E2E assertions.
