# Feature Specification: UPD-051 — Data Lifecycle (Tenant and Workspace)

**Feature Branch**: `104-data-lifecycle`
**Spec Directory**: `specs/104-data-lifecycle/`
**Created**: 2026-05-03
**Status**: Draft
**Input**: User description: "UPD-051 — Data Lifecycle (Tenant and Workspace)"

---

## Brownfield Context

**Current state (post-audit-pass + SaaS-pass refreshes):**

- **UPD-023 (Privacy Compliance)**: implements DSR for individual users (GDPR Article 15–22). Cascade deletion across PostgreSQL/Qdrant/Neo4j/ClickHouse/OpenSearch/S3 + tombstones with cryptographic hash. Owner of the cross-store cascade machinery.
- **UPD-042 (User Notifications)**: user-level self-service DSR submission lives there.
- **UPD-024 (Audit Chain)**: hash-linked, tamper-evident audit chain. Every privileged action records an entry. Constitutional rule 30 — audit-chain writes MUST be durable.
- **UPD-046 (Tenant Architecture)**: multi-tenant data model, RLS policies, BYPASSRLS staff role, tenant feature flags.
- **UPD-047 (Plans/Subscriptions/Quotas)**: plan caps + subscription state.
- **UPD-049 refresh (PR #135) and UPD-050 refresh (PR #136)**: marketplace scope + abuse prevention layer respectively, both merged.

**Gap that UPD-051 closes**: there is no tenant-scoped or workspace-scoped data export, no tenant deletion path beyond the existing tenant lifecycle states (suspended/blocked/archived), no workspace deletion at all, no DPA management surface, no public sub-processors page, and the existing audit chain has no documented behaviour for what happens during a tenant cascade.

**FR coverage**: FR-751 through FR-760 (functional-requirements section 124).

**Scope boundary.** This feature owns:

- Workspace data export (Free/Pro tiers; ZIP via async job; S3 presigned URL)
- Workspace deletion (Free/Pro; two-phase with 7-day grace)
- Tenant data export (Enterprise; ZIP via async job; encrypted, password-protected)
- Tenant deletion (Enterprise; two-phase with 30-day grace; cascades data + DNS + TLS + Vault)
- DPA per Enterprise tenant (custom PDF upload; default tenant uses standard clickwrap)
- Public sub-processors page
- GDPR Article 28 evidence package for Enterprise contracts
- Backup separation: deleted tenants' data purged from backups within 30 days

**Out of scope** (delegated to other features):

- Per-user DSR (UPD-023 owns this)
- Subscription cancellation mechanics (UPD-052; this feature's deletion path REQUIRES the subscription to be cancelled first per FR-757.1)
- DNS/TLS plumbing for tenant subdomain teardown (UPD-053; this feature's phase-2 cascade DELEGATES to UPD-053's teardown service)
- Cross-store cascade deletion machinery (UPD-023; this feature INVOKES `cascade_deletion.py` rather than reimplementing it)

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Workspace owner exports their workspace data (Priority: P1)

A Free or Pro user wants to download all their workspace data — agents, executions, audit log, costs, member list — as a single archive. They use this as a portability snapshot before evaluating an alternative platform, or as a record before deleting the workspace.

**Why this priority**: Self-service export is the GDPR Article 20 (data portability) anchor for workspace-level data. Without it, the only path to a snapshot is a privileged-staff DB dump — operationally untenable and a privacy red flag. P1 because every paying customer expects to walk away with their data.

**Independent Test**: A Pro-plan workspace owner navigates to the workspace data-export surface, requests an export, and receives an email when the async job completes. The email contains a signed URL valid for 7 days. The download succeeds; the resulting ZIP contains structured JSON files per resource type plus raw artifacts. A different workspace's owner cannot access the URL.

**Acceptance Scenarios**:

1. **Given** a workspace owner viewing their workspace settings, **When** they request a data export, **Then** an export job is created in `pending` status, an audit-chain entry records the request with the actor identity, and the user is shown an "export queued" confirmation.
2. **Given** an export job has completed, **When** the user receives the notification, **Then** the email contains a signed URL valid for 7 days from completion timestamp, the URL points to the workspace's exported archive, and clicking it downloads the archive.
3. **Given** a completed export, **When** the user downloads it and unzips, **Then** the archive contains at least: `agents/` (one JSON per agent + raw revision blobs), `executions/` (one JSON per execution + task plans), `audit/` (audit-chain entries scoped to this workspace), `costs/` (cost records), `members/` (member list with redaction per FR-751.4), `metadata.json` (export timestamp + workspace identity + content manifest hash).
4. **Given** the workspace has multiple members, **When** the export is generated, **Then** member email addresses appear ONLY for members who have explicitly consented to data sharing within their workspace, AND the archive does NOT include any data from other workspaces those users belong to.
5. **Given** an export's signed URL has passed its TTL, **When** the user clicks the link, **Then** the storage backend returns the signed-URL-expired error and an audit-chain entry records the access attempt; the user is shown a "request a new export" CTA.

---

### User Story 2 — Workspace owner deletes their workspace (Priority: P1)

A workspace owner no longer needs the workspace and wants to delete it permanently. They expect a grace window during which they can cancel — a typo or a heat-of-the-moment decision must be reversible.

**Why this priority**: Deletion without grace is the worst kind of irreversible action. Two-phase deletion with grace is the industry standard. P1 because the workspace is the user's single point of control over their data; deletion has to work cleanly.

**Independent Test**: A workspace owner clicks Delete on their workspace, types the workspace name to confirm, and submits. The workspace transitions to `pending_deletion`; an email confirmation arrives with a cancel link valid for 7 days. The workspace becomes inaccessible to all members from the moment of phase-1 transition. After 7 days, the cascade deletion runs and the workspace's resources are purged. A 90-day audit tombstone remains, then is purged.

**Acceptance Scenarios**:

1. **Given** a workspace owner views their settings, **When** they click Delete, type the workspace name, and confirm, **Then** the workspace transitions to `pending_deletion`, an email with a cancel link valid for 7 days is sent to the owner, and an audit-chain entry records the phase-1 request with the actor identity.
2. **Given** a workspace is in `pending_deletion`, **When** any member (including the owner) attempts to access workspace resources, **Then** access is refused with a clear "this workspace is scheduled for deletion in N days" message; the cancel link in the original email remains the only way to abort the deletion.
3. **Given** the 7-day grace window has elapsed, **When** the cascade runs, **Then** all workspace resources are deleted (agents, executions, costs, members, settings, etc.) and a 90-day audit tombstone is retained that names the workspace, the deletion timestamp, and the actor who initiated it.
4. **Given** the 90-day audit tombstone window has elapsed, **When** the daily purge runs, **Then** the tombstone is removed from the active audit chain and only a hash-linkage anchor remains so chain integrity verification continues to pass.
5. **Given** a workspace is in `pending_deletion`, **When** the owner clicks the cancel link, **Then** the workspace returns to `active` and an audit-chain entry records the cancellation; the workspace becomes accessible again immediately.

---

### User Story 3 — Enterprise tenant cancellation with full export (Priority: P1)

An Enterprise customer (e.g., Acme Corp) cancels their contract. They expect a final tenant-wide data export delivered to the tenant administrator and a generous grace window during which the cancellation can be reversed for compliance or contractual reasons.

**Why this priority**: This is the Enterprise contractual exit path. The platform's value proposition for Enterprise customers includes contractual data ownership and clean exit — failing this path damages the SaaS reputation. P1 because Enterprise contracts are revenue-critical.

**Independent Test**: A super admin initiates tenant deletion at `/admin/tenants/{slug}/delete`. Phase 1 marks the tenant `pending_deletion`, generates a final tenant-wide export, and sends a download link (encrypted, password-protected) to the tenant admin. The tenant becomes inaccessible to its users. A 30-day grace window applies. The super admin can recover the tenant during grace. After grace, phase 2 cascades data + DNS + TLS + secrets, and a regulatory-retention audit tombstone is moved to cold storage for 7 years.

**Acceptance Scenarios**:

1. **Given** a super admin views the Enterprise tenant Acme, **When** they initiate tenant deletion (with double-confirmation typed slug + 2PA token), **Then** the tenant transitions to `pending_deletion`, a tenant-wide export job is enqueued, an audit-chain entry records phase-1 with the super admin's identity and the contract reference, and the tenant admin receives a notification with the export-download workflow.
2. **Given** the tenant-wide export job completes, **When** the tenant admin opens the notification, **Then** they receive a download link encrypted with a one-time password sent via a separate channel (email + SMS or admin-of-record postal address per contract), valid for 30 days, and the archive contents are equivalent to all the tenant's workspace exports concatenated plus tenant-level metadata.
3. **Given** the 30-day grace window has elapsed, **When** phase 2 runs, **Then** the tenant cascade deletes: every workspace, every user except for tenant-staff with audit-only roles, every agent, every execution, every cost record, every Vault secret, every DNS record, every issued TLS cert (revoked first via UPD-053), every OAuth provider callback registration, and the tenant row itself.
4. **Given** the tenant cascade has completed, **When** the regulatory audit-tombstone retention check runs, **Then** the tenant's audit-chain history is moved to a separate cold-storage location with a 7-year retention policy and the active audit chain's running hash is preserved by an anchor entry.
5. **Given** the tenant is in `pending_deletion`, **When** the super admin clicks Recover before the 30-day grace ends, **Then** the tenant returns to `active`, the export-download link is revoked, the secrets/DNS/TLS state is unchanged (phase 2 hasn't run), and an audit-chain entry records the recovery with the super admin's identity and the recovery reason.
6. **Given** the tenant has an active subscription, **When** the super admin attempts phase 1 without first cancelling the subscription, **Then** the deletion request is refused with a clear "subscription is still active — cancel via UPD-052 first" error and no audit-chain entry is recorded as a phase-1 attempt.

---

### User Story 4 — Sub-processors page is publicly accessible (Priority: P2)

A potential customer evaluating the platform wants to verify which third parties handle their data before they sign up. They expect a public, version-stamped page they can show to their compliance team.

**Why this priority**: Public sub-processor lists are a SaaS standard for B2B sales. Without one, Enterprise sales calls hit friction. P2 because the platform functions without it — it's a sales-enablement requirement, not a runtime gate.

**Independent Test**: An unauthenticated visitor navigates to the public sub-processors page. They see the current list of third-party services categorised (LLM provider, infrastructure, billing, fraud, etc.) with each entry showing company name, category, location of data processing, and a link to the third party's privacy policy or DPA. The "Last updated" timestamp is prominent. Visitors can subscribe to changes via RSS or email.

**Acceptance Scenarios**:

1. **Given** an unauthenticated visitor opens the public sub-processors page, **When** the page renders, **Then** they see at minimum: Anthropic (LLM), OpenAI (LLM, where enabled), Hetzner (infrastructure), Stripe (billing), the email-delivery provider, MaxMind (fraud — only when fraud-scoring is enabled), and any other active sub-processors.
2. **Given** the page renders an entry, **When** the visitor inspects it, **Then** they see: company legal name, category, primary processing location (country), the categories of platform data the provider sees, and an outbound link to that provider's privacy policy and (where available) DPA.
3. **Given** the sub-processors list has been updated, **When** the page renders, **Then** the "Last updated" timestamp reflects the most recent active/inactive change, and a change-log shows the prior 6 months of additions and removals.
4. **Given** a visitor wants to be notified of changes, **When** they subscribe via RSS or email on the page, **Then** the system records the subscription and emits a notification on every future change. RSS works without an account.
5. **Given** a sub-processor is added or removed, **When** the change is saved by an authorised platform staff, **Then** the page is regenerated within 5 minutes and the change-log + RSS feed reflect it.

---

### User Story 5 — DPA upload at Enterprise tenant creation (Priority: P1)

A super admin creates an Enterprise tenant under a contract that requires a tenant-specific DPA. They upload the negotiated DPA PDF as part of tenant creation, and the system records the document's content hash on the tenant for audit and contractual proof.

**Why this priority**: GDPR Article 28 requires a written DPA between controller (the tenant) and processor (the platform). For Enterprise, that DPA is often custom-negotiated. Without an upload-and-hash workflow, the DPA lives in a manually-managed shared drive — a compliance risk. P1 because an Enterprise tenant cannot legally process personal data without a DPA in place.

**Independent Test**: A super admin opens tenant creation, completes the standard fields, attaches a PDF DPA, and submits. The system accepts PDFs up to 50 MB, computes a SHA-256 content hash, stores the file encrypted in the platform's secret store, records the hash + timestamp + version on the tenant row, and writes an audit-chain entry. The default tenant does NOT use this path — its users accept a standard clickwrap DPA pinned per signup.

**Acceptance Scenarios**:

1. **Given** a super admin creates an Enterprise tenant, **When** they upload a PDF up to 50 MB as the DPA, **Then** the upload succeeds, a SHA-256 hash is computed, the document is stored encrypted in the platform secret store at a tenant-namespaced path, and the tenant row records `dpa_signed_at`, `dpa_version`, and the SHA-256 hash.
2. **Given** the DPA upload contains malware or an invalid PDF, **When** the upload is processed, **Then** the upload is refused with a clear error and the tenant creation is rolled back; no tenant row is created.
3. **Given** an Enterprise tenant exists with an active DPA, **When** the super admin uploads a new version, **Then** the new version is stored under a versioned path, the tenant's DPA hash and version are updated, the prior version stays addressable for audit, and an audit-chain entry records the version change.
4. **Given** the default tenant signup flow, **When** a user accepts the clickwrap DPA at signup, **Then** the standard DPA's version (a content-hash anchor) is recorded on the user's signup record and the user gets a downloadable copy of the standard DPA via the user's settings page.
5. **Given** an Enterprise tenant is being deleted, **When** the cascade reaches the secret store, **Then** the tenant's DPA versions are deleted from the secret store and the audit tombstone retains only the content hashes for compliance proof.

---

### Edge Cases

- **Export job fails midway** (e.g., transient S3 outage, agent revision blob missing): the job is retried up to 3 times with exponential backoff. After the third failure, the job's status becomes `failed`, the user is notified that the export could not complete, and a partial archive is NOT delivered (privacy: half an export is worse than none). The user can request a fresh export.
- **Tenant deletion attempted while subscription is active**: refused at phase 1 with a clear "cancel the subscription first via UPD-052" error. No audit entry recorded for the refusal (the action never happened).
- **Grace period extension**: a super admin can extend the grace period during the grace window per ops policy (e.g., to give a tenant admin more time for review). Each extension is audited. The maximum cumulative grace is bounded by ops policy (default 90 days).
- **Backup retention conflict**: GDPR right-to-be-forgotten obligates deletion within 30 days of the cascade; some regulatory regimes require 7-year retention of audit data. Mitigation: backups containing deleted-tenant data are re-encrypted with a fresh key, the previous key is destroyed, and the resulting "tombstone" is retained for the regulatory window — the data is unrecoverable but the existence/hash is provable.
- **DNS removal failure during phase 2**: the cascade emits a structured-log alert and retries with exponential backoff up to 24 hours. If still failing, the operator is paged; manual cleanup is documented in the runbook. The cascade does NOT block on DNS — it proceeds with the rest and records DNS as a known follow-up.
- **DPA upload contains malware**: every uploaded file is scanned via the platform's existing virus-scan pipeline (UPD-023's DLP integration) before storage. On detection, the upload is refused with a clear error, no file is persisted, and an audit entry records the rejection with the file hash and the malware signature matched.
- **Member email leak across workspaces**: workspace export must redact member emails for users whose public-display preference is not opted in. The export logic queries the user's UPD-042 visibility settings before including their email; users with private profiles appear as opaque user-id only.
- **Audit-chain integrity during cascade**: deleting a tenant deletes its own audit-chain entries, but the entries' hash linkages must be preserved by an anchor entry inserted into the active chain noting "tenant {id} cascade completed at {ts}, prior hash {hash}". This anchor lets future verification confirm the chain is intact even after partial deletions.
- **Cross-tenant agent forks pre-existing the deletion**: when an Enterprise tenant is deleted, agents in the public marketplace (UPD-049) that reference its agents as a fork source survive — only the `forked_from_agent_id` becomes a dangling reference, with the marketplace UI rendering "Source agent removed" gracefully (the on-delete cascade per UPD-049 is `SET NULL`, which honours this requirement).
- **Workspace owner who is the only member**: workspace deletion proceeds as documented; user data not in this workspace is unaffected per the membership model (UPD-046).
- **Sub-processors page caching**: the public page is regenerated within 5 minutes of any change; visitors hitting between regeneration cycles see the previous version with a clearly visible last-updated timestamp.

---

## Requirements *(mandatory)*

### Functional Requirements

**Workspace export (FR-751)**

- **FR-751**: The system MUST allow a workspace owner to request an asynchronous data export of their workspace.
- **FR-751.1**: The export MUST be delivered as a single archive containing structured per-resource files (agents, executions, audit, costs, members, settings) plus a manifest naming every file and its content hash.
- **FR-751.2**: On completion, the user MUST receive a notification with a signed URL valid for 7 days.
- **FR-751.3**: The signed URL MUST be scoped to the requester only — opening it from another account or after the TTL MUST be refused with a clear error.
- **FR-751.4**: Member email addresses included in the export MUST honour each member's privacy settings (UPD-023 / UPD-042); users opting out of cross-context email exposure appear as opaque user-id.
- **FR-751.5**: Every export request and completion MUST emit an audit-chain entry.

**Workspace deletion (FR-752)**

- **FR-752**: The system MUST support workspace deletion as a two-phase operation: phase 1 marks the workspace `pending_deletion`, phase 2 (after grace) cascades the deletion.
- **FR-752.1**: Phase 1 requires typed-name confirmation; on confirmation the workspace becomes inaccessible to all members.
- **FR-752.2**: Phase 1 MUST send a cancel-link email to the owner valid for 7 days (the grace window).
- **FR-752.3**: During grace, the owner can cancel the deletion; cancellation restores access immediately and is audited.
- **FR-752.4**: After grace, phase 2 MUST cascade-delete the workspace's agents, executions, costs, members, settings, and any per-workspace stores (memory, etc.) via the existing UPD-023 cascade machinery.
- **FR-752.5**: A 90-day audit tombstone MUST be retained naming the workspace and the deletion event; after 90 days the tombstone is purged but a hash-linked anchor remains in the chain.

**Tenant export (FR-753)**

- **FR-753**: The system MUST allow a super admin OR a tenant admin to request a tenant-wide data export.
- **FR-753.1**: The tenant export MUST contain every workspace export concatenated plus tenant-level metadata (members, billing snapshot, DPA version, sub-processor list at time of export).
- **FR-753.2**: The export's download URL MUST be encrypted and password-protected; the password MUST be delivered via a separate channel (email + SMS or admin-of-record contact per contract).
- **FR-753.3**: Tenant-export URLs MUST be valid for 30 days from completion.
- **FR-753.4**: Every tenant-export request and completion MUST emit an audit-chain entry.

**Tenant deletion (FR-754)**

- **FR-754**: The system MUST support tenant deletion as a two-phase operation: phase 1 marks the tenant `pending_deletion` and emits a final export; phase 2 (after grace) cascades the deletion.
- **FR-754.1**: Phase 1 requires double-confirmation: typed slug + 2PA token (per UPD-040 two-person authorisation).
- **FR-754.2**: Phase 1 MUST be refused if the tenant has an active subscription. The super admin must cancel the subscription via UPD-052 first; the refusal MUST surface that exact remediation.
- **FR-754.3**: Phase 1 MUST be refused for the platform's default tenant. The default tenant cannot be deleted via this surface.
- **FR-754.4**: During grace, the super admin can recover the tenant; recovery restores access, revokes any export-download links issued during grace, and is audited.
- **FR-754.5**: Phase 2 MUST cascade-delete: workspaces, users (except platform-staff users with cross-tenant audit roles), agents, executions, cost records, Vault secrets, DNS records (delegating to UPD-053), TLS certs (revoked via UPD-053), OAuth callbacks (UPD-041), and the tenant row itself.
- **FR-754.6**: The tenant's audit-chain history MUST be moved to a separate cold-storage location with a 7-year retention; the active audit chain MUST receive an anchor entry preserving the running hash.
- **FR-754.7**: Phase 2 MUST emit the existing privacy tombstone for each deleted personal-data record per UPD-023.

**Grace period (FR-755)**

- **FR-755**: Grace periods MUST default to 7 days for workspace deletion and 30 days for tenant deletion. Both MUST be configurable per contract by a super admin.
- **FR-755.1**: A super admin MUST be able to extend the grace window during grace; each extension is audited; cumulative grace is bounded by ops policy (default 90 days).

**DPA management (FR-756)**

- **FR-756**: The system MUST accept a tenant-specific DPA PDF upload at Enterprise tenant creation (and on subsequent versioning).
- **FR-756.1**: The upload MUST accept PDFs up to 50 MB.
- **FR-756.2**: Every upload MUST be virus-scanned; on detection, the upload is refused and the tenant creation is rolled back.
- **FR-756.3**: The DPA file MUST be stored encrypted in the platform secret store under a tenant-namespaced versioned path.
- **FR-756.4**: The tenant row MUST record `dpa_signed_at`, `dpa_version`, and the document's SHA-256 hash.
- **FR-756.5**: Versioning replaces the active version but the prior version stays addressable for audit until tenant deletion.
- **FR-756.6**: The default tenant MUST use a standard clickwrap DPA whose version is recorded per user signup.

**Sub-processors page (FR-757)**

- **FR-757**: The platform MUST publish a public sub-processors page accessible without authentication.
- **FR-757.1**: The page MUST list each currently-active sub-processor with: legal name, category, primary processing location, data categories handled, and an outbound link to the third party's privacy policy and (where available) DPA.
- **FR-757.2**: The page MUST display a prominent "Last updated" timestamp reflecting the most recent active/inactive change.
- **FR-757.3**: The page MUST offer RSS and email subscription for change notifications.
- **FR-757.4**: A change-log MUST show the prior 6 months of additions, removals, and category changes.
- **FR-757.5**: After any sub-processor change is saved by authorised platform staff, the public page MUST be regenerated within 5 minutes.
- **FR-757.6**: The page MUST be reachable during a full platform outage (independent topology per constitutional rule 49).

**GDPR Article 28 evidence package (FR-758)**

- **FR-758**: The platform MUST be able to generate, on demand, a per-Enterprise-tenant evidence package documenting the controller-processor relationship per GDPR Article 28.
- **FR-758.1**: The evidence package MUST include: the active DPA (with hash), the active sub-processors list (snapshot at request time), the active audit-chain export (last 12 months), the tenant's data residency configuration, the maintenance-window history, and a signed manifest naming every artifact and its content hash.
- **FR-758.2**: Generating the evidence package MUST be auditable (audit-chain entry on request and delivery).

**Backup separation (FR-759)**

- **FR-759**: When a tenant cascade completes, the platform MUST schedule the deletion of that tenant's data from all backups within 30 days of cascade completion.
- **FR-759.1**: Backups subject to regulatory retention conflicts MUST use the tombstone-via-key-destruction approach: the tenant's encrypted segment is re-keyed and the prior key destroyed, leaving the data unrecoverable while the tombstone remains for retention proof.

**Audit chain integrity (FR-760)**

- **FR-760**: All deletions performed by this feature MUST preserve the audit-chain hash linkage. Where entries are deleted, an anchor entry MUST be inserted into the active chain naming the deletion event and the prior chain hash so future verification confirms the chain is intact.
- **FR-760.1**: The audit chain MUST remain verifiable after any combination of workspace and tenant cascades — i.e., `audit-chain verify` against the active chain and any cold-storage chains MUST succeed.

### Key Entities

- **Data export job**: a record naming the scope (workspace or tenant), the requesting user, the status (pending/processing/completed/failed), the output URL with TTL, the output size, and the manifest hash. Audit-tracked.
- **Deletion job**: a record naming the scope, the phase (phase_1, phase_2, completed, aborted), the requesting user, the grace period and end timestamp, and the cascade timestamps. Audit-tracked.
- **Sub-processor entry**: a record naming a third-party service: legal name, category, primary location, data categories, privacy-policy URL, optional DPA URL, active flag, started-using-at date, optional notes. Public-readable.
- **DPA version**: a tenant-scoped record naming the document path in the secret store, the SHA-256 hash, the signed-at timestamp, and the version number.
- **Audit anchor entry**: an entry inserted into the active audit chain naming a deletion event (workspace or tenant) and the prior chain hash, ensuring chain integrity survives the deletion.
- **Tenant lifecycle audit history (cold storage)**: the moved audit-chain history of a deleted tenant, retained for the regulatory window (default 7 years), with hash linkage preserved internally.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of workspace export jobs complete within 10 minutes for workspaces with up to 1 GB of source data; 95% within 60 minutes for up to 10 GB. Failed jobs surface a user-actionable error within 30 seconds of the failure.
- **SC-002**: 100% of completed export download links honour the documented TTL (7 days for workspace, 30 days for tenant) — no link works after expiry, and 0% of links are issued without an audit-chain entry.
- **SC-003**: 100% of workspace deletions reach phase 2 cascade exactly once when grace expires without cancellation; 0 workspaces are stuck in `pending_deletion` past `grace_ends_at + 24h` (alerting threshold for ops).
- **SC-004**: 100% of tenant deletions emit a final export AND require subscription cancellation AND require 2PA confirmation before phase-1 commits — measurable by an audit-reconciliation report that compares phase-1 events against subscription-state and 2PA-token-consumed events for the same tenant.
- **SC-005**: 100% of tenant cascades complete the data, DNS, TLS, Vault legs within 24 hours of grace expiry. DNS leg failures (per the edge case) MUST trigger an ops alert within 15 minutes.
- **SC-006**: The public sub-processors page renders within 2 seconds at the 95th percentile for unauthenticated visitors; the change-propagation latency from save to live page is at most 5 minutes; the RSS feed is available 99.9% of the time.
- **SC-007**: 100% of Enterprise tenants have a DPA recorded with `dpa_signed_at`, `dpa_version`, and content hash before their first non-trivial workload runs (verifiable by a tenant-readiness gate that refuses workload submission until DPA is recorded).
- **SC-008**: Audit-chain verification (`audit-chain verify`) MUST succeed against the active chain and every cold-storage chain after any combination of cascades. The verification MUST be runnable as a daily CI gate.
- **SC-009**: Backup-purge for a deleted tenant completes within 30 days of cascade completion at the 99th percentile, measured by an end-to-end backup-content audit that confirms no cleartext deleted-tenant data is retrievable past day 30.
- **SC-010**: J27 — the Tenant Lifecycle Cancellation end-to-end journey covering all five user stories — passes on every CI run.

---

## Assumptions

- **Cascade machinery exists.** UPD-023 (`privacy_compliance/cascade_deletion.py`) implements cross-store cascade (PostgreSQL + Qdrant + Neo4j + ClickHouse + OpenSearch + S3) and tombstone emission. This feature INVOKES that machinery for the workspace/tenant cascades; it does NOT reimplement cross-store deletion.
- **Audit chain machinery exists.** UPD-024 (`security_compliance/services/audit_chain_service.py`) provides hash-linked tamper-evident audit logging. This feature emits new entry kinds and the cascade-completion anchor entries through the existing service.
- **DNS/TLS plumbing is owned by UPD-053.** This feature's tenant-cascade phase 2 DELEGATES to UPD-053's tenant-domain teardown service. If UPD-053 has not landed, phase 2 logs a follow-up rather than block.
- **Subscription cancellation is owned by UPD-052.** This feature's FR-754.2 refuses phase-1 if the subscription is still active; the refusal text points the operator to UPD-052.
- **Vault is the platform secret store.** UPD-040 (HashiCorp Vault Integration) is in place and accessible via the existing `SecretProvider`. DPA documents are stored at `secret/data/musematic/{env}/tenants/{slug}/dpa/dpa-v{n}.pdf`.
- **Object storage is S3-compatible.** Per constitutional rule 25 / Principle XVI, exports use generic S3 via `S3_ENDPOINT_URL` configuration. Presigned URLs are S3-native.
- **Email delivery is reliable.** UPD-042 user notifications channel is the canonical path for export-ready emails and cancel-link emails. SMS for tenant-export password is delivered via the existing notification multi-channel surface (UPD-077 if present, else a follow-up).
- **Virus scanning is available.** UPD-023's DLP integration provides a virus-scan endpoint reusable for DPA upload validation.
- **2PA mechanism is available.** UPD-040 / UPD-086 provides two-person-authorisation tokens. Tenant-deletion phase 1 consumes a 2PA token.
- **Public sub-processors page topology.** The page is hosted on a dedicated static-site path independent of the main app's deployment topology (constitutional rule 49). Updates flow from the platform DB to the static site via an automated regeneration job triggered on save (within the 5-minute SLO).
- **Audit cold-storage destination.** Tenant-cascade audit history moves to an S3-compatible cold-storage bucket (`platform-audit-cold-storage`) with object-lock retention configured to 7 years. Bucket-level retention guarantees immutability per regulatory requirements.
- **Marketplace fork-source dangling references behave per UPD-049.** When an Enterprise tenant is deleted, public-marketplace agents that were forked from agents in the deleted tenant retain their `forked_from_agent_id` references with `ON DELETE SET NULL` per UPD-049's data model — the marketplace UI handles dangling references gracefully without this feature changing the FK.
- **Per-user DSR remains owned by UPD-023.** Individual users (not workspace owners, not tenant admins) follow the existing DSR path. This feature is exclusively about workspace-and-up scopes.
- **Default tenant has its own clickwrap DPA flow.** UPD-048 (default-tenant signup) records the user's clickwrap DPA acceptance with a content-hash anchor; this feature does NOT redefine that flow but cites it for completeness.
- **Backup retention vs. RTBF.** The platform's existing backup machinery (UPD-048 backup/restore) supports per-tenant key destruction for tombstone-via-key-destruction. This feature relies on that primitive for FR-759.1.
- **Free tier export availability.** Free-tier workspaces can request exports at the same rate-limit as Pro (1 export per 24h per workspace). Free tier may have lower priority on the export queue if the queue is backlogged.
- **English-first for the public sub-processors page.** Localisation follows UPD-035 i18n; initial release is English with translations queued.
