# Feature Specification: UPD-048 — Public Signup at Default Tenant Only

**Feature Branch**: `098-default-tenant-signup`
**Created**: 2026-05-02
**Status**: Draft
**Input**: User description: "UPD-048 — Public Signup at Default Tenant Only. Restrict public signup to the default tenant; auto-create Free workspace post-verification; onboarding wizard; Enterprise tenant first-admin invitation flow at `/setup`; cross-tenant membership model; `/me/memberships` introspection; tenant switcher in shell. FR-723 through FR-732."

## Background and Motivation

The audit-pass platform shipped UPD-037 (Public Signup + OAuth UI completion) on the assumption that signup was a single, global flow: anyone visiting `/signup` becomes a member of the platform. UPD-046 made the platform multi-tenant; this feature aligns the signup surface with that posture. Three constitutional rules pin the desired behaviour:

- **SaaS-3** — *tenants are not self-serve*: public users cannot create tenants; they sign up as users within the default tenant.
- **SaaS-4 + SaaS-7** — Free / Pro plans live in the default tenant, differentiated by per-workspace subscription. Enterprise tenants exist outside the default tenant and provision users via tenant-admin invitation.
- **SaaS-37** — *cookies scoped per subdomain*: a user with memberships in multiple tenants logs in independently per tenant, never with a cross-subdomain cookie.

UPD-048 reshapes the signup surface to honour those rules. Public signup is reachable ONLY at the default-tenant subdomain (`app.musematic.ai/signup`); any attempt to reach `/signup` on an Enterprise tenant subdomain (`acme.musematic.ai/signup`, `globex.musematic.ai/signup`, …) returns the same opaque 404 the platform produces for unknown hostnames — preserving the tenant-existence privacy posture established in UPD-046. Successful default-tenant signups auto-provision a Free workspace plus its Free subscription (UPD-047) so the user lands directly on a working surface; an onboarding wizard guides first-run choices (workspace name, teammate invitations, first agent, optional product tour).

Enterprise tenants get a parallel — but invitation-only — onboarding path. When super admin provisions an Enterprise tenant (UPD-046 User Story 1), the platform sends a single-use invitation to the first tenant admin. That invitation lands at `<slug>.musematic.ai/setup` and runs a hardened flow: Terms of Service acceptance, password creation (or OAuth linking when the tenant has an OAuth provider configured), **mandatory** MFA enrolment for the tenant-admin role, first-workspace creation, and an optional teammate-invitation step. After completion, the tenant admin can use the existing UPD-042 invitation infrastructure to bring more users into their tenant.

The membership model becomes explicitly cross-tenant: a single human can hold memberships in the default tenant AND in one or more Enterprise tenants. Each membership is a separate user record in the relevant tenant's identity store (per UPD-046's per-tenant scoping); they share an email address but nothing else. The user authenticates separately at each tenant subdomain (cookies are subdomain-scoped per FR-692) and may use different identity providers per tenant (per SaaS-36). A `/me/memberships` endpoint returns the union of memberships, and a tenant switcher in the shell renders a one-click subdomain redirect when the user holds 2+ memberships.

This feature is constitutional alignment work — most of UPD-037's plumbing (verification, anti-enumeration, OAuth, password rules, admin approval) is preserved and extended with tenant-awareness rather than rewritten.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Public signup at the default tenant (Priority: P1)

A public user discovers the platform on its marketing site, clicks "Sign up", lands at `app.musematic.ai/signup`, and creates an account. After verifying the email, the user lands on a working workspace with default branding and the onboarding wizard.

**Why this priority**: The default-tenant signup is the primary commercial entry point for the SaaS surface. Without it, the SaaS pass cannot acquire any Free or Pro customers.

**Independent Test**: Browser navigates to `app.musematic.ai/signup`. Form submitted with email, password, and Terms-of-Service consent. Verification email arrives. User clicks the verification link. The user is redirected to the onboarding wizard. After the wizard's first step, the user has a working Free workspace with a Free subscription and a workspace-owner role.

**Acceptance Scenarios**:

1. **Given** the request hostname is the default-tenant subdomain, **When** a user submits the signup form with valid inputs, **Then** an account-creation request is processed against the default tenant, an email-verification message is sent, and the response is anti-enumeration neutral (the same response shape regardless of whether the email already exists in the default tenant).
2. **Given** a user clicks a valid email-verification link, **When** the link is consumed, **Then** the user record is marked verified within the default tenant, a Free workspace is auto-created with that user as owner, a Free subscription is provisioned for the workspace via UPD-047's plumbing, and the browser is redirected to the onboarding wizard.
3. **Given** a Free workspace is auto-created, **When** the workspace materialises, **Then** the workspace name defaults to a sensible per-user value the user can change in the wizard (e.g., the user's display name plus "'s workspace"), and the user holds the workspace-owner role with the Free plan's quotas in force.
4. **Given** OAuth signup is enabled at the default tenant, **When** the user completes the OAuth round-trip, **Then** the same auto-provisioning happens — verification is implicit (OAuth provider attests), Free workspace is created, onboarding wizard launches.

---

### User Story 2 — Signup attempt at an Enterprise tenant subdomain returns an opaque 404 (Priority: P1)

A user (well-meaning or hostile) navigates to `acme.musematic.ai/signup`. Acme is an Enterprise tenant; public signup is not allowed there. The platform responds with the same opaque 404 used for unknown hostnames — no leak of whether `acme` is a provisioned tenant, no leak of the no-public-signup policy, no special error page.

**Why this priority**: Constitutional rule SaaS-3 forbids self-serve tenant joining. SaaS-19 (UPD-046) requires opaque 404 responses to avoid information leakage about provisioned tenants. Without this gating, an attacker could enumerate Enterprise tenants by probing for `/signup` reachability or by fingerprinting the response shape.

**Independent Test**: Issue a request with `Host: acme.musematic.ai` against `/signup` (and any nested signup paths). Expect HTTP 404 with the platform's canonical opaque 404 body — byte-identical to the response from `bogus.musematic.ai/signup`. Confirm via response-hash comparison across at least 10 candidate Enterprise subdomain-plus-`/signup` probes.

**Acceptance Scenarios**:

1. **Given** the request hostname resolves to a tenant of kind `enterprise`, **When** the request path is `/signup` (or any sub-path), **Then** the response is HTTP 404 with the canonical opaque body — no tenant-specific copy, no stack-trace, no "signup disabled" wording.
2. **Given** the request hostname is unresolved, **When** the request path is `/signup`, **Then** the response is identical (byte-for-byte) to the Enterprise-tenant case, preserving the constitutional opacity guarantee.
3. **Given** the response was opaque, **When** the request log is inspected, **Then** the entry contains the standard request line and timing only (no special "blocked signup" tag), so log-volume attacks cannot be used to fingerprint the policy.

---

### User Story 3 — Enterprise tenant first-admin onboarding via `/setup` (Priority: P1)

After super admin provisions an Enterprise tenant (UPD-046 User Story 1), the platform sends an invitation to the first tenant admin. The admin clicks the invitation link, lands at `<slug>.musematic.ai/setup`, completes a hardened multi-step flow (Terms of Service, password or OAuth linking, **mandatory** MFA enrolment, first-workspace creation, optional teammate invitations), and ends on the tenant-admin dashboard.

**Why this priority**: Without this flow, no Enterprise tenant can become operational after provisioning. It is the second half of the gating capability for paying Enterprise customers (the first half being UPD-046 User Story 1).

**Independent Test**: Trigger UPD-046 tenant provisioning for an Acme tenant. Receive the first-admin invitation in a test mailbox. Click the invitation link; land at `acme.musematic.ai/setup?token=…`. Complete every step. Verify (a) the token can only be used once; (b) the token expired-link path renders a clear "Request a new invitation" message; (c) MFA enrolment cannot be skipped — the wizard refuses to advance without a verified TOTP/recovery-code pair; (d) at least one workspace exists in the tenant after the flow; (e) a hash-linked audit chain entry exists for each completed step.

**Acceptance Scenarios**:

1. **Given** a valid first-admin invitation token, **When** the user opens the invitation link, **Then** the setup flow renders at the tenant subdomain with the tenant's branding (per UPD-046 User Story 5) — confirming to the user they are joining the right organisation.
2. **Given** an invalid or expired token, **When** the user opens the link, **Then** a "Request a new invitation" page is rendered and the super admin's `/admin/tenants/{id}` page exposes a "Resend invitation" affordance (audited).
3. **Given** the user is at the MFA-enrolment step, **When** the user attempts to skip, **Then** the wizard refuses; the only paths forward are "complete enrolment" or "abandon and contact super admin".
4. **Given** the user completes the full flow, **When** the wizard finishes, **Then** the user holds the tenant-admin role within the tenant, a first workspace exists in the tenant with the user as workspace owner, and an audit chain entry tagged with the tenant identifier is recorded for each step (TOS accepted, password set / OAuth linked, MFA enrolled, workspace created, optional invites sent, setup completed).
5. **Given** the user reloads the page mid-flow, **When** the page renders, **Then** wizard state is preserved and the user resumes at the last incomplete step (no need to restart from TOS).

---

### User Story 4 — Cross-tenant invitation extends an existing default-tenant user into an Enterprise tenant (Priority: P1)

A consultant `juan@acme.com` already has an account in the default tenant. The Acme tenant admin invites `juan@acme.com` to join the Acme tenant. Juan accepts; Juan now holds memberships in BOTH the default tenant AND the Acme tenant — the two are independent identities sharing an email address.

**Why this priority**: A consultant or part-time contributor working with multiple Enterprise customers is a common SaaS user shape; without cross-tenant membership the platform forces them to use different email addresses per tenant. This story validates the per-tenant-identity model (constitutional rule SaaS-36 / UPD-046 spec edge case "first-admin email already exists in default tenant").

**Independent Test**: Pre-provision `juan@acme.com` in the default tenant (User Story 1 path). As an Acme tenant admin, send an invitation to `juan@acme.com`. Receive the invitation in a test mailbox. Click the link; land at `acme.musematic.ai/accept-invite?token=…`. Authenticate via Acme's identity provider (which may differ from the default tenant's). Accept membership. Verify (a) Juan now has TWO user records — one in default, one in Acme — with the same email but distinct identifiers and credentials; (b) Juan's default-tenant membership and workspace memberships are unchanged; (c) Juan's session at `acme.musematic.ai` is independent of any session at `app.musematic.ai` (cookies subdomain-scoped per FR-692).

**Acceptance Scenarios**:

1. **Given** Juan already exists in the default tenant, **When** the Acme tenant admin issues an invitation, **Then** a fresh invitation token is created scoped to the Acme tenant; the existing default-tenant user record is unaffected.
2. **Given** Juan accepts the Acme invitation, **When** the acceptance is processed, **Then** a new user record is created within the Acme tenant with its own credential row and its own MFA state; Juan's default-tenant credentials and MFA state are untouched.
3. **Given** Juan has cookies for the default tenant, **When** Juan visits `acme.musematic.ai`, **Then** Juan is treated as unauthenticated until separately signing in at the Acme subdomain.
4. **Given** the default tenant uses email/password and Acme uses an external SSO provider, **When** Juan signs in at each subdomain, **Then** each tenant honours its configured identity provider independently.

---

### User Story 5 — Onboarding wizard guides the first-run experience and is dismissible (Priority: P2)

After verifying their email or completing OAuth signup at the default tenant, the user lands on an onboarding wizard. The wizard walks through workspace naming, optional teammate invitations, optional first-agent creation, and an optional product tour. The wizard can be dismissed at any step; its state persists across page reloads; and it can be re-launched later from the user's settings.

**Why this priority**: Polish on the post-signup experience — improves activation rate but is not gating for the SaaS commercial layer. P2 because P1 stories cover the actual creation of the user and workspace; this story covers the introduction.

**Independent Test**: Sign up via User Story 1; land on the wizard. Confirm: step 1 shows a pre-populated default workspace name; step 2 surfaces the UPD-042 invitation flow; step 3 surfaces the existing agent-creation wizard from UPD-022; step 4 starts an optional product tour; the "Dismiss" affordance appears on every step. Reload mid-step — confirm wizard resumes at the same step. Dismiss; confirm the wizard re-launches from `Settings → Onboarding → Restart`.

**Acceptance Scenarios**:

1. **Given** the user has just verified their email, **When** the wizard opens, **Then** step 1 renders with a sensible default workspace name pre-populated; the user may rename or accept the default.
2. **Given** the user is on any step, **When** the user clicks "Dismiss", **Then** the wizard closes and the user lands on the workspace dashboard; the wizard's state-of-completion is saved so a later resume is possible.
3. **Given** the user reloads the page mid-wizard, **When** the page re-renders, **Then** the wizard resumes at the same step with previously-entered fields preserved.
4. **Given** the user has dismissed the wizard, **When** the user navigates to Settings, **Then** an "Onboarding" entry exposes a "Re-launch wizard" action that resumes the wizard at the first incomplete step.
5. **Given** the user invites teammates from the wizard's step 2, **When** invitations are sent, **Then** the existing UPD-042 invitation infrastructure delivers them; cancelling out of step 2 without inviting is permitted and does not block progression.

---

### User Story 6 — Multi-tenant user switches between tenants via a shell tenant-switcher (Priority: P3)

A consultant Juan works across the default tenant plus two Enterprise customers (Acme and Globex). When Juan signs in at any of the three subdomains, the platform shell shows a tenant switcher listing all of Juan's memberships; clicking another tenant redirects to that tenant's subdomain (where Juan must sign in separately because cookies are subdomain-scoped).

**Why this priority**: Quality-of-life for the rare-but-real consultant persona. P3 because most users only ever hold one tenant membership and never see the switcher; the read-only memberships introspection is a separate concern that lands as P1-supporting infrastructure (per User Story 4).

**Independent Test**: Pre-provision Juan with memberships in default, Acme, and Globex. Sign in at `app.musematic.ai`. Verify the shell renders a tenant switcher in a discoverable location with all three tenants listed. Click "Acme"; verify the browser redirects to `acme.musematic.ai/login`. Sign in at Acme. Verify the switcher reflects the same three tenants.

**Acceptance Scenarios**:

1. **Given** the signed-in user has 2 or more memberships, **When** any page in the shell renders, **Then** the tenant switcher is visible with the user's full list of memberships and the current tenant marked.
2. **Given** the signed-in user has exactly 1 membership, **When** any page in the shell renders, **Then** the tenant switcher is hidden — single-tenant users do not see the affordance.
3. **Given** the user clicks a different tenant in the switcher, **When** the switch is initiated, **Then** the browser is redirected to the target tenant's login page; no session crosses the subdomain boundary; cookies remain scoped per FR-692.
4. **Given** an introspection request, **When** the user calls the memberships endpoint, **Then** the response lists every tenant where the user has a membership, including each tenant's slug, display name, kind, and the user's role within that tenant.

---

### Edge Cases

- **Email already in default tenant on signup** — the default-tenant signup endpoint returns the same neutral "If the address is new, a verification email is on its way" message regardless of whether the email exists; preserves the UPD-037 anti-enumeration posture.
- **Email already exists in Enterprise tenant Acme but signup is attempted at default** — independent identity stores per UPD-046; the default-tenant signup succeeds without conflict; the user holds two membership records sharing an email address.
- **OAuth provider not configured for the default tenant** — the signup page renders without the OAuth button; only email/password remains visible. No blank "OAuth disabled" placeholder is shown.
- **Invitation token expired or already used** — the invitation acceptance page renders a clear "Request a new invitation" message with no detail about which mailbox originally received it.
- **First-tenant-admin loses or never receives the invite link** — super admin can resend the invitation from the existing `/admin/tenants/{id}` page; the resend invalidates the prior token and is recorded in the audit chain. The MFA gate still applies on the resent flow.
- **Free workspace auto-creation fails (e.g., transient DB error)** — the user verification still succeeds; a deferred-retry job creates the workspace within a documented latency budget; the user sees a "Setting up your workspace" splash until the workspace materialises.
- **Sign up succeeds but the Free subscription provisioning fails** — verification rolls forward; the workspace exists; the subscription is created by a deferred-retry job. Until the subscription exists, the workspace is in a paused state with a clear UI banner explaining the situation.
- **A user attempts to accept an Enterprise invitation while signed in to a different tenant** — the acceptance flow refuses with a clear "Sign out of <other tenant> first" message; cross-tenant sessions never coexist.
- **Default tenant accidentally suspended (constitution forbids this, but the platform must degrade safely)** — signup gracefully degrades to an explanatory error page; not the opaque 404 (the page is reachable; the operation is not).
- **Wizard step depending on UPD-022 (agent creation) is unavailable in a deployment that has not landed UPD-022** — the wizard's step 3 hides cleanly without breaking the rest of the flow.

## Requirements *(mandatory)*

### Functional Requirements

#### Public signup at the default tenant

- **FR-001**: The platform MUST render the public signup surface ONLY when the resolved request tenant has kind `default`. Any other tenant kind (currently `enterprise`) MUST receive the platform's canonical opaque 404.
- **FR-002**: The default-tenant signup form MUST accept an email address, a password meeting the existing UPD-037 password rules, and an explicit Terms-of-Service consent confirmation.
- **FR-003**: The default-tenant signup endpoint MUST be anti-enumeration: the response body and timing MUST NOT distinguish "email already exists in this tenant" from "email is new", preserving the UPD-037 posture.
- **FR-004**: When a default-tenant signup completes email verification, the platform MUST create a Free workspace owned by the new user and provision a Free subscription for that workspace by calling into UPD-047's subscription-provisioning surface.
- **FR-005**: The Free workspace's name MUST default to a sensible per-user value (e.g., a display-name-derived placeholder); the user MUST be able to change this name during the onboarding wizard.
- **FR-006**: When the default tenant has at least one OAuth provider configured (per UPD-041), the signup form MUST surface the corresponding OAuth buttons; OAuth signup MUST follow the same auto-provisioning path as email/password signup.
- **FR-007**: When OAuth is selected, email verification MUST be considered implicit (the provider attests the email) and Free-workspace auto-provisioning MUST proceed without an additional verification round-trip.

#### Enterprise tenant signup gating

- **FR-008**: The signup surface (and any sub-paths) MUST return the platform's canonical opaque 404 when reached at any non-default tenant subdomain. The response shape MUST be byte-identical to the unknown-hostname 404 specified by UPD-046 SC-009.
- **FR-009**: The signup-attempt event at an Enterprise subdomain MUST NOT generate a special log entry, audit chain entry, or telemetry tag that would let an external observer fingerprint the policy.

#### Enterprise tenant first-admin onboarding

- **FR-010**: When super admin provisions an Enterprise tenant (UPD-046), the platform MUST issue a first-admin invitation token bound to the new tenant's subdomain, with a documented single-use lifetime (default 7 days, configurable per operator).
- **FR-011**: The first-admin invitation link MUST land at the tenant subdomain's `/setup` path with the token attached. The setup surface MUST be reachable ONLY when a valid, unconsumed, unexpired token is presented.
- **FR-012**: The setup flow MUST collect, in order: Terms-of-Service acceptance, password creation OR OAuth linking (only when the tenant has an OAuth provider configured), MFA enrolment, first-workspace creation, optional teammate invitations, and a final "you're done" confirmation.
- **FR-013**: MFA enrolment MUST be mandatory in the setup flow for the tenant-admin role; the wizard MUST refuse to advance past this step without a verified TOTP and recovery-code generation. The user MAY abandon the flow but MUST NOT skip the step.
- **FR-014**: The platform MUST emit a hash-linked audit chain entry (tenant-scoped) for each completed setup step: TOS accepted, credentials configured, MFA enrolled, first workspace created, invitations sent, setup completed.
- **FR-015**: Setup-flow state MUST persist across page reloads so the user resumes at the last incomplete step rather than restarting from the beginning.
- **FR-016**: Super admin MUST be able to resend a first-admin invitation from `/admin/tenants/{id}`; resending MUST invalidate the prior token, generate a new one, and record an audit chain entry naming the prior and new token identifiers.

#### Cross-tenant invitations and membership model

- **FR-017**: A user invited to a tenant via the existing UPD-042 invitation flow MUST receive a NEW user record within that tenant, with its own credential row, MFA state, and session lifecycle. Existing memberships in other tenants MUST be unaffected.
- **FR-018**: The platform MUST allow the same email address to belong to multiple tenants concurrently as independent identity records.
- **FR-019**: Sessions MUST be subdomain-scoped per UPD-046 FR-692; signing in at one tenant's subdomain MUST NOT establish a session at any other tenant's subdomain.
- **FR-020**: The platform MUST accept different identity providers per tenant (email/password at default, OAuth at one Enterprise tenant, SAML at another, …) without requiring a single global identity-provider configuration.

#### Memberships introspection and tenant switcher

- **FR-021**: The platform MUST expose a self-service introspection endpoint that returns the authenticated user's full list of tenant memberships, each entry containing the tenant's slug, display name, kind, the user's role within that tenant, and a deep link to that tenant's login surface.
- **FR-022**: The introspection endpoint MUST resolve memberships across tenants by joining on the email address (for canonical cross-tenant identity) AND the user's identity records in each tenant; the response MUST hide tenants the user does not belong to (no tenant-existence leak).
- **FR-023**: The shell MUST render a tenant switcher when (and only when) the authenticated user has 2 or more memberships. The current tenant MUST be visibly marked.
- **FR-024**: Clicking a tenant in the switcher MUST redirect the browser to the target tenant's login surface; no session, cookie, or identifier MUST cross the subdomain boundary.

#### Onboarding wizard

- **FR-025**: After successful default-tenant verification (email or OAuth), the platform MUST redirect the user to an onboarding wizard at the default-tenant subdomain.
- **FR-026**: The wizard MUST be dismissible at every step. Dismissal MUST persist the wizard's state-of-completion so the user can resume later.
- **FR-027**: The wizard's first step MUST allow the user to rename their auto-created Free workspace.
- **FR-028**: The wizard's invitation step MUST surface the existing UPD-042 invitation flow scoped to the new workspace; cancelling the step MUST be permitted.
- **FR-029**: The wizard's agent-creation step MUST surface the existing agent-creation flow (UPD-022); when UPD-022 is not deployed, the step MUST be hidden cleanly without breaking the rest of the wizard.
- **FR-030**: The wizard MUST be re-launchable from the user's Settings surface at any later time; re-launch MUST resume at the first incomplete step.
- **FR-031**: Wizard state MUST persist across page reloads so the user can navigate away and return without starting over.

#### Audit and constitutional compliance

- **FR-032**: Every signup, verification, OAuth linkage, setup-flow step, invitation acceptance, and tenant-membership transition MUST emit a hash-linked audit chain entry tagged with the relevant tenant identifier (per UPD-046 R7).
- **FR-033**: The signup, setup, and acceptance surfaces MUST never disclose whether a target tenant exists beyond what the canonical opaque 404 already reveals (constitution rule SaaS-19 / UPD-046 SC-009).

### Key Entities

- **Default-tenant signup attempt**: A user-submitted intent to become a default-tenant member. Contains email, hashed password (or OAuth attestation), Terms-of-Service consent record, anti-enumeration neutral response state.
- **Enterprise first-admin invitation**: A single-use, time-bounded token tied to a specific Enterprise tenant and a target email address, used to bootstrap the tenant's first administrative user. Has expiration timestamp, consumption timestamp, issuer reference (super admin), invalidation history (in case of resend).
- **User membership**: An association of a user record with a specific tenant. A single human may hold multiple membership records (one per tenant); each membership owns its own credential row, MFA state, and role assignments. Memberships share an email address but nothing else.
- **Onboarding wizard state**: A per-user record of which wizard steps are complete, the user-provided values at each step, and whether the wizard has been dismissed. Persisted so re-entry resumes at the last incomplete step.
- **Tenant switcher membership listing**: A read-only projection used to render the shell's tenant switcher and the `/me/memberships` introspection. Each entry carries the tenant's slug, display name, kind, the user's role, and the deep-link URL.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user completing default-tenant signup with valid inputs reaches a working Free workspace within **two minutes** of clicking the email-verification link, in **at least 95%** of attempts under normal operating conditions.
- **SC-002**: A request to `/signup` (and any sub-path) at any non-default tenant subdomain returns HTTP 404 with a body byte-identical to the unknown-hostname 404 in **100%** of probes; this is verified across at least 50 candidate hostnames combining real Enterprise tenants and randomly-generated unknown subdomains.
- **SC-003**: A first-admin invitation generated by tenant provisioning (UPD-046 User Story 1) reaches the target mailbox within **five minutes** in at least **95%** of cases; the resulting setup flow drives the user from invitation click to a fully-configured tenant admin (workspace exists, MFA enrolled) in under **ten minutes** of active interaction.
- **SC-004**: MFA enrolment cannot be skipped in the setup flow: an automated probe attempting every "skip" or "next" affordance from the MFA step **always** fails to advance until a TOTP secret is verified.
- **SC-005**: A user holding memberships in 3 tenants completes a switcher click and sees the target tenant's login surface in **under 3 seconds** of click time, with no cookie crossing the subdomain boundary (verified by browser-tooling assertion).
- **SC-006**: An invited cross-tenant user (matching User Story 4) ends with **exactly two** independent identity records (one per tenant), as verified by SQL count grouped on `(tenant, email)`.
- **SC-007**: The onboarding wizard's dismissal is honoured **100%** of the time across every step; a dismissed wizard's state-of-completion is preserved so re-launch from settings always resumes at the first incomplete step.
- **SC-008**: The auto-provisioned Free workspace exists and is reachable for **at least 99%** of completed default-tenant signups within the deferred-retry latency budget; the remainder receive a clear "Setting up your workspace" splash until the deferred job completes.
- **SC-009**: A super admin's "Resend invitation" action invalidates the prior token within a **single round-trip** and produces a new token whose acceptance leads to the same setup flow as the original; an attempt to use the prior token after resend produces the standard "expired" surface.
- **SC-010**: The `/me/memberships` introspection endpoint returns every membership the authenticated user holds with **zero false negatives** (no membership omitted) and **zero false positives** (no tenant the user does not belong to surfaced); this is verified by integration test against synthetic users with 0, 1, 2, 3, and 5 memberships.

## Assumptions

- UPD-046 (`tenants` table, hostname middleware, opaque 404, RLS posture, per-tenant cookies) is fully landed before this feature begins. The "opaque 404" canonical body is owned by UPD-046 and reused here unmodified.
- UPD-047 (`subscriptions` table, `SubscriptionService.provision_for_default_workspace`) is landed; this feature calls into UPD-047 to provision the Free subscription on Free-workspace auto-creation.
- UPD-037 (signup core: email verification, OAuth, anti-enumeration neutral response, password rules) remains the substrate. This feature wraps UPD-037 with tenant-awareness and adds the auto-provisioning + onboarding path; it does not rewrite UPD-037's fundamentals.
- UPD-042 (workspace invitation infrastructure) is the delivery mechanism for both the wizard's step 2 and the Enterprise tenant cross-tenant invitations. This feature does not re-implement invitation delivery.
- UPD-022 (agent-creation wizard) is the surface used by the onboarding wizard's step 3. When UPD-022 is not deployed, step 3 is hidden gracefully.
- The first-admin invitation default lifetime is 7 days and is configurable per operator. The exact configurable knob lives in the platform settings owned by this feature.
- The Free-workspace auto-creation latency budget is on the order of seconds; transient failures fall back to a deferred-retry job whose latency budget is documented in the operator runbook.
- Cross-tenant identity uses email-as-correlator only for the introspection endpoint (`/me/memberships`); email is NOT the join key for any tenant-scoped data path. Each tenant's user record is independent and addressable by its own identifier.
- The audit chain hash already includes `tenant_id` (UPD-046 R7); this feature's audit entries leverage the existing chain format without further changes.
- The default tenant's branding renders on `/signup`, `/onboarding`, and `/setup-disabled` (for the rare case the default tenant is somehow unreachable). Enterprise tenant branding renders on `/setup` for the first-admin flow per UPD-046 User Story 5.
- Tenant switching is a redirect, not a session swap. Users are expected to authenticate independently at each tenant they want to use.
