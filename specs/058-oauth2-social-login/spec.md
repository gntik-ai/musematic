# Feature Specification: OAuth2 Social Login (Google and GitHub)

**Feature Branch**: `058-oauth2-social-login`
**Created**: 2026-04-18
**Status**: Draft
**Input**: Brownfield extension of the auth bounded context (feature 014). Adds external identity providers (Google, GitHub) as supported sign-in methods alongside the existing local username/password flow, with admin-controlled enablement, first-login auto-provisioning, account linking, domain/org access restrictions, and external-group-to-platform-role mapping.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Administrator enables and configures an external identity provider (Priority: P1)

A platform administrator wants to allow members of their organization to sign in with their existing Google or GitHub identity instead of managing a separate platform password. The administrator configures a provider by providing issued credentials, a redirect URL the identity provider will return users to, the set of domains or organizations permitted to sign in, and a default role for first-time sign-ins. They can enable or disable the provider at any time.

**Why this priority**: Without provider configuration, no user can sign in via an external identity. This is the gating prerequisite for all other OAuth flows and is the first admin action required to activate the feature.

**Independent Test**: An administrator opens the admin settings, configures a provider with valid credentials, saves, and verifies the provider appears as an available option on the login page. With the provider disabled, it does not appear on the login page.

**Acceptance Scenarios**:

1. **Given** a platform administrator is in admin settings, **When** they configure Google with a valid client identifier, secret reference, redirect URL, and default role and save, **Then** Google is persisted as an enabled provider and is shown on the login page for unauthenticated users.
2. **Given** an enabled provider configuration, **When** the administrator disables it, **Then** the provider is immediately removed from the login page and all in-flight authorization flows for that provider fail on callback with a clear message.
3. **Given** a configured provider, **When** the administrator updates its client secret reference, **Then** subsequent authorization exchanges use the new secret and no previously-logged value appears in any configuration view or API response.
4. **Given** provider configuration, **When** any client secret value would otherwise appear in an API response, log entry, or configuration export, **Then** the platform returns only the reference identifier and never the secret value.

---

### User Story 2 — New user signs in with Google or GitHub and is auto-provisioned (Priority: P1)

A person without a platform account clicks "Sign in with Google" (or "Sign in with GitHub"), authenticates with the provider, consents to share profile information, and returns to the platform. The platform recognizes them as a new identity, creates a platform user using their name and email, assigns the default role configured on the provider, and lands them on the platform home page — all without the person having created a local password.

**Why this priority**: This is the highest-value flow for new adoption. It removes the friction of a separate password and speeds up onboarding from minutes to seconds for the vast majority of users who already have a Google or GitHub identity.

**Independent Test**: On a clean platform with Google configured and with a test Google account that has never signed in before, click "Sign in with Google", complete the consent flow, and verify that a new platform user is created with the correct email, name, default role, and a valid active session.

**Acceptance Scenarios**:

1. **Given** Google is enabled and a Google account has never used the platform, **When** the user clicks "Sign in with Google" and grants consent, **Then** the platform creates a new user with the email, display name, and default role from the provider configuration, records the external identity link, and issues a platform session within 15 seconds of the user clicking the button.
2. **Given** GitHub is enabled and a GitHub account has never used the platform, **When** the user completes GitHub sign-in, **Then** the platform provisions a new user using GitHub's primary verified email and profile name, and issues a platform session.
3. **Given** a configured domain restriction that does NOT include the signing-in user's Google Workspace domain, **When** the user completes Google sign-in, **Then** the platform rejects the sign-in with a clear message explaining the restriction and issues no session.
4. **Given** a configured organization restriction that does NOT include any of the signing-in user's GitHub organizations, **When** the user completes GitHub sign-in, **Then** the platform rejects the sign-in with a clear message and issues no session.
5. **Given** a configured group-to-role mapping where the user's external group membership matches an entry, **When** a new user is auto-provisioned, **Then** the mapped platform role is assigned instead of the provider's default role.

---

### User Story 3 — Existing user links an external identity to their account (Priority: P2)

A user who already has a platform account (created via local password or a different OAuth provider) wants to add Google or GitHub as an additional sign-in method. They navigate to their profile's connected-accounts section, start the link flow, authenticate with the provider, and return to find the provider now listed among their connected identities.

**Why this priority**: Important for adoption by existing teams, but secondary — local-password users continue to sign in normally until they choose to link. Not blocking for initial rollout.

**Independent Test**: Sign in with a local account, visit the profile connected-accounts section, initiate "Link Google", complete the provider flow, and verify the provider now appears as linked and the user can sign out and sign in again using either method.

**Acceptance Scenarios**:

1. **Given** an authenticated user on their profile page, **When** they initiate linking a provider and complete the provider's authentication, **Then** the external identity is recorded against their existing user account without creating a duplicate, and future sign-ins with that provider log into the same account.
2. **Given** an attempt to link an external identity that is already linked to a different platform user, **When** the user completes the provider flow, **Then** the platform rejects the link with a clear message and does not merge or reassign the existing link.
3. **Given** a user completing a first-time provider sign-in whose email matches an existing local account, **When** the callback runs, **Then** the platform does not silently create a duplicate — it prompts the user to authenticate locally first to confirm linking intent.

---

### User Story 4 — Administrator restricts access by domain/organization and maps external groups to platform roles (Priority: P2)

A platform administrator wants external sign-ins to be gated to their own organization (not the public Google user population) and wants new users to land in the correct workspace role automatically based on their identity-provider group membership. They configure Google Workspace domain allow-lists, GitHub organization allow-lists, and a mapping from external group or team names to platform workspace roles.

**Why this priority**: Critical for enterprise tenants but not required for initial individual-user validation. Security teams block rollout without it; smaller teams can adopt without it.

**Independent Test**: Configure the provider with a domain allow-list that excludes a test user's domain; verify that user's sign-in is rejected. Change the allow-list to include the user's domain; verify sign-in succeeds. Configure a group-to-role mapping matching the test user's external group; verify the user is auto-provisioned with the mapped role.

**Acceptance Scenarios**:

1. **Given** a Google provider with a configured domain allow-list of `["company.com"]`, **When** a user whose Google Workspace domain is `othercompany.com` attempts sign-in, **Then** the platform rejects the sign-in and creates no user or session.
2. **Given** a GitHub provider with an organization allow-list of `["my-org"]`, **When** a user who is not a member of `my-org` attempts sign-in, **Then** the platform rejects the sign-in.
3. **Given** a group-to-role mapping where `"engineering"` maps to `workspace_admin`, **When** a new Google user whose groups include `"engineering"` is auto-provisioned, **Then** the user is created with the `workspace_admin` workspace role.
4. **Given** an existing linked user whose external group membership has changed at the provider, **When** the user signs in again, **Then** the platform updates the stored group membership and (subject to policy) re-evaluates their workspace role based on the mapping.

---

### User Story 5 — User unlinks an external identity (Priority: P3)

A user who previously linked a provider wants to revoke that link — for example because they are retiring the external account or switching to a different identity. They visit their profile, select the provider, and confirm unlinking. The link is removed and they can no longer sign in with that provider, but their platform account remains active if they still have at least one other authentication method.

**Why this priority**: Completeness of the lifecycle, but rarely exercised. Safely deferrable after the link and sign-in flows are stable.

**Independent Test**: As a user with two linked authentication methods (e.g., local password + Google), initiate unlink for Google, confirm, and verify that attempting Google sign-in no longer authenticates to that account while local sign-in still works.

**Acceptance Scenarios**:

1. **Given** a user with multiple authentication methods (e.g., local + at least one linked provider), **When** they unlink one provider, **Then** the link is removed, other authentication methods continue working, and future sign-ins via the unlinked provider for that external identity are treated as a new identity.
2. **Given** a user whose only authentication method is a single linked provider, **When** they attempt to unlink it, **Then** the platform rejects the request with a clear message requiring them to add another authentication method first.

---

### User Story 6 — Security operator audits OAuth sign-in activity (Priority: P3)

A security operator investigating a suspected account compromise wants to see every OAuth sign-in attempt against a specific user or provider — when, from what IP and user agent, whether it succeeded or failed, which provider was used, and which external identity was asserted. The audit feed exposes this without exposing any client secrets or provider-issued tokens.

**Why this priority**: Needed before production cutover for regulated deployments; essential but not blocking for initial user-facing rollout.

**Independent Test**: Perform a sequence of successful and failed sign-ins (valid Google user, user blocked by domain restriction, user with invalid state), query the audit feed for the user and time window, and verify each attempt is recorded with provider name, outcome, IP, user agent, and external identity reference — with no secret values present.

**Acceptance Scenarios**:

1. **Given** any OAuth sign-in attempt, **When** the attempt completes (success or failure), **Then** an audit entry is persisted within 5 seconds containing provider, external identity reference, IP, user agent, outcome, and a failure reason for failed attempts.
2. **Given** the audit records, **When** the operator queries them, **Then** no record contains a client secret, authorization code, access token, ID token, or refresh token value.
3. **Given** a provider configuration change (enable/disable, allow-list change, role mapping change), **When** the change is applied, **Then** a configuration-change audit event is persisted naming the administrator, the provider, and the fields that changed (with secret references masked).

---

### Edge Cases

- **Provider email change at the provider**: If the external identity provider reports a different primary email than previously recorded for the same external identity, the platform MUST update the stored email rather than treating the identity as new, because the external identity reference (not the email) is the stable key.
- **Provider disabled mid-flow**: If an administrator disables a provider while a user has an in-flight authorization exchange, the callback MUST fail with a clear message and MUST NOT issue any session.
- **Stale authorization session**: If more than the configured time-to-live elapses between sign-in start and provider callback, the platform MUST reject the callback and require the user to restart the flow.
- **Callback with no code or with provider error**: If the user cancels consent at the provider or the provider returns an error, the callback MUST surface a non-sensitive error message and issue no session.
- **Duplicate email collision on auto-provision**: If a new provider sign-in produces an email address that already belongs to a different platform user account, the platform MUST NOT silently merge or duplicate; it MUST prompt the user to sign in to the existing account first and then link the provider.
- **External identity already linked to another user**: If a user attempts to link an external identity that is already linked to a different platform user, the platform MUST reject the link and MUST NOT reassign the existing link.
- **Same external identity signing in after being unlinked**: An unlinked identity that later signs in again MUST be treated as a brand-new identity — either auto-provisioned (if allowed by configuration) or prompted to link.
- **Provider requires additional factor (MFA) per platform policy**: If the provider configuration has `require_mfa = true`, the platform MUST challenge the user for its own MFA factor after the external sign-in succeeds, before issuing a platform session — even if the external provider also enforced MFA.
- **Rate-limit burst on callback endpoint**: If a single source exceeds the callback rate limit, additional requests from that source MUST be rejected with a retry-after indicator and MUST NOT consume authorization-session state.
- **Session after provider disablement**: Disabling a provider MUST NOT invalidate already-issued platform sessions for users who signed in via that provider — those sessions remain valid until natural expiry or logout, consistent with how local-auth sessions behave.
- **Admin revokes a user mid-session**: If an administrator removes or suspends a user whose session was issued via an OAuth provider, the platform MUST invalidate that session on the next request, identical to the local-auth suspension flow.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Platform MUST support authentication via external identity providers using the OAuth2 authorization code flow with Proof Key for Code Exchange (PKCE), in addition to the existing local username/password authentication.
- **FR-002**: Platform MUST support Google and GitHub as identity providers in the initial scope; the configuration surface MUST be structured so that additional providers can be added without schema changes.
- **FR-003**: Administrators MUST be able to enable or disable each provider independently at any time.
- **FR-004**: Administrators MUST be able to configure per-provider display name, issued credentials (client identifier + client secret reference), redirect URL, requested scopes, domain/organization restrictions, external-group-to-platform-role mapping, default role for new users, and an MFA-requirement toggle.
- **FR-005**: Client secrets MUST be stored as references to a secure secret store; the platform MUST NOT accept, persist, log, export, or return in API responses any plaintext secret value.
- **FR-006**: Platform MUST generate and validate an OAuth `state` parameter on every authorization flow (single-use, integrity-protected, time-limited) to defend against cross-site request forgery.
- **FR-007**: Platform MUST generate a fresh PKCE code verifier per authorization flow and MUST bind it to the `state` parameter; the callback MUST fail if the verifier is missing, expired, or does not match.
- **FR-008**: Platform MUST validate the identity assertion returned by Google (ID token) against Google's published signing keys, including issuer, audience, and expiration claims.
- **FR-009**: Platform MUST retrieve authoritative user profile information (email, display name, avatar reference) from the provider using the issued access token for both Google and GitHub.
- **FR-010**: Platform MUST retrieve Google Workspace hosted-domain claim and external group membership (when scopes permit) and GitHub organization membership and team membership (when scopes permit) for restriction and role-mapping enforcement.
- **FR-011**: When a provider has a domain restriction configured, the platform MUST reject any sign-in whose provider-asserted domain is not in the allow-list, before creating any user or session.
- **FR-012**: When a provider has an organization restriction configured, the platform MUST reject any sign-in whose provider-asserted organizations do not intersect the allow-list, before creating any user or session.
- **FR-013**: When a provider has a group-to-role mapping configured, the platform MUST assign the mapped platform role to users whose external group membership matches at auto-provision time; when no mapping matches, the provider's default role MUST apply.
- **FR-014**: On first successful sign-in for a new external identity, the platform MUST auto-provision a new platform user using the provider-returned email and name, record the external identity link, and assign the computed role.
- **FR-015**: When a sign-in produces an email that matches an existing local (unlinked) user, the platform MUST NOT silently create a duplicate; it MUST require authentication against the existing account before establishing the link.
- **FR-016**: Authenticated users MUST be able to initiate linking of an additional provider to their account.
- **FR-017**: Authenticated users MUST be able to unlink a previously-linked provider from their account, provided at least one other authentication method remains; attempts to unlink the last method MUST be rejected with a clear message.
- **FR-018**: Platform MUST issue a platform session after successful external sign-in that is indistinguishable in format, lifetime, and downstream authorization behavior from sessions issued via local sign-in.
- **FR-019**: When a provider configuration has the MFA-requirement toggle enabled, the platform MUST challenge the user for a platform MFA factor after external sign-in succeeds and MUST NOT issue a session until MFA is completed.
- **FR-020**: Platform MUST rate-limit the callback endpoint to prevent abuse; the rate limit MUST be configurable and MUST reject requests beyond the limit with a retry-after indicator and without consuming any authorization-session state.
- **FR-021**: Platform MUST audit every sign-in attempt (both success and failure) with: provider identifier, external identity reference, source IP, user agent, outcome, and failure reason if applicable. Audit records MUST NOT contain client secrets, authorization codes, access tokens, ID tokens, or refresh tokens.
- **FR-022**: Platform MUST audit every provider configuration change (enable/disable, restriction change, role-mapping change, credential-reference change) with the acting administrator and the changed fields, masking any secret references.
- **FR-023**: Public (unauthenticated) listing of available providers MUST return only enabled providers and MUST expose only display information (type, display name) — never credentials, secret references, or restriction details.
- **FR-024**: Login user interface MUST display only providers returned by the public listing endpoint.
- **FR-025**: Authenticated profile user interface MUST show a user's connected providers with the ability to initiate link/unlink flows for each.
- **FR-026**: Platform MUST emit domain events for significant OAuth lifecycle transitions (user auto-provisioned via provider, user linked provider, user unlinked provider, sign-in failed due to restriction, provider configuration changed) for downstream audit and observability consumers.
- **FR-027**: When a provider is disabled, already-issued platform sessions for users who signed in via that provider MUST remain valid until natural expiry or explicit logout — consistent with existing local-auth session behavior.
- **FR-028**: Platform MUST update stored external-identity attributes (email, display name, avatar reference, external group membership) on every successful sign-in so downstream behavior (role mapping, display) reflects the provider's current state.

### Key Entities

- **OAuth Provider Configuration**: Administrator-managed record describing one external identity provider — provider type (Google, GitHub), display name, enabled flag, issued client identifier, client secret reference (never a secret value), redirect URL, requested scopes, domain/organization allow-lists, external-group-to-role mapping, default role for new users, MFA-requirement toggle, audit timestamps.
- **External Identity Link**: Association between one platform user and their identity at one provider — provider, external identity reference, last-known external email/name/avatar/group membership, link and last-login timestamps. A platform user MAY have multiple links (one per provider) and MAY additionally have a local password; a provider MAY link many platform users (one per external identity).
- **Authorization Session**: Short-lived server-side record tying an outbound sign-in request to a user's browser — state parameter, PKCE verifier, provider reference, expiry. Single-use: consumed on callback and deleted; never reusable.
- **OAuth Audit Entry**: Immutable record of every OAuth event — sign-in attempt (success/failure with reason), configuration change (by whom, what changed), link/unlink (user, provider, initiator). Carries external identity references but never secret values.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can complete first-time sign-in with Google and reach the platform home page within 15 seconds of clicking the sign-in button.
- **SC-002**: A new user can complete first-time sign-in with GitHub and reach the platform home page within 15 seconds of clicking the sign-in button.
- **SC-003**: 100% of authorization code exchanges use PKCE and 100% of callbacks validate the state parameter before any token operation or user mutation.
- **SC-004**: No client secret, authorization code, access token, ID token, or refresh token value ever appears in any API response, structured log entry, audit record, or configuration export — verifiable by an automated scan over the platform output surface.
- **SC-005**: When a Google Workspace domain restriction is configured, 100% of sign-in attempts from disallowed domains are rejected before any user or session is created.
- **SC-006**: When a GitHub organization restriction is configured, 100% of sign-in attempts from users outside the allow-list are rejected before any user or session is created.
- **SC-007**: When a group-to-role mapping matches an auto-provisioning user's external group membership, the mapped platform role is assigned instead of the default role in 100% of cases.
- **SC-008**: Every sign-in attempt (success or failure) appears in the audit feed within 5 seconds of the attempt.
- **SC-009**: A user with multiple authentication methods can unlink one provider and still sign in with a remaining method 100% of the time; the platform rejects unlink requests that would leave the user with no authentication method 100% of the time.
- **SC-010**: An administrator can complete initial configuration of a provider (credentials, restrictions, role mapping) in under 5 minutes per provider.
- **SC-011**: The rate-limited callback endpoint rejects requests beyond the configured limit within any time window, verifiable by a load test.
- **SC-012**: The proportion of user sign-ins completed via external providers versus local password is available as a dashboard metric after rollout (operational observability goal — the specific target is tenant-dependent).

## Assumptions

- Users signing in with Google have an active Google account; users signing in with GitHub have an active GitHub account. The platform accepts identities, it does not create them at the provider.
- The configured redirect URL is a platform-owned endpoint reachable by the user's browser over HTTPS.
- Clock skew between the platform and the identity providers is within ±60 seconds, acceptable for standard JWT expiration validation.
- For Google, external "group membership" means Google Workspace group membership retrievable via the provider's directory scope; providers not granting that scope produce an empty group list (the user receives only the default role).
- For GitHub, external "group membership" means team membership under the configured allow-listed organizations; users with no team memberships receive the default role.
- Secret storage is provided by the existing cluster secret mechanism; a future enhancement may route through a dedicated secret manager but that substitution is transparent to this feature.
- Auto-provisioning is intentional default behavior: administrators who prefer link-only (no auto-provisioning) express that by not configuring a default role and rejecting unrecognized identities (future enhancement — not in MVP).
- The existing MFA factor implementation (from the auth bounded context) is reused for OAuth flows when the provider's MFA-requirement toggle is enabled; no new MFA factor types are introduced.

## Dependencies

- The existing auth bounded context (users, sessions, credentials, MFA flow, audit feed) is the substrate this feature extends; all new records reference existing user and session entities.
- The existing admin settings panel is the configuration surface for enabling providers and setting restrictions/role mappings.
- The existing login user interface adds provider buttons conditionally based on the public listing endpoint.
- The existing profile user interface adds a connected-accounts section for link/unlink flows.
- The existing RBAC engine validates that mapped roles exist and are grantable before an auto-provisioned user is created.
- External availability of Google OAuth2 endpoints and GitHub OAuth endpoints is a third-party dependency; the platform handles provider outages gracefully (clear error, no partial state) but cannot guarantee provider uptime.

## Out of Scope

- Additional identity providers beyond Google and GitHub (e.g., Microsoft Entra, Okta, Auth0) — will be added in a later feature using the same configuration surface.
- SAML 2.0 — tracked as a separate enterprise SSO feature.
- SCIM user provisioning (push-based directory sync from provider to platform).
- Social-graph integrations (importing contacts, calendars, repositories).
- OAuth2 client-credentials grant for machine-to-machine authentication — the platform's service-account API key mechanism continues to serve that need.
- Replacing local password authentication — local sign-in remains fully supported.
- Provider-initiated (IdP-initiated) SSO flows — only service-provider-initiated flows are supported.
- Dedicated secret-manager integration (e.g., Vault) — cluster secrets remain the backing store for this feature; a Vault layer is a possible future enhancement and does not affect the configuration contract.
- Automated migration of existing local-password users to OAuth-only accounts — users choose to link voluntarily.
