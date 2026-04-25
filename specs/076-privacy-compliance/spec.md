# Feature Specification: Privacy Compliance (GDPR / CCPA)

**Feature Branch**: `076-privacy-compliance`
**Created**: 2026-04-25
**Status**: Draft
**Input**: User description: "New `privacy_compliance/` bounded context implementing the six GDPR / CCPA data-subject rights (access, rectification, erasure, portability, restriction, objection), right-to-be-forgotten with cascade deletion across PostgreSQL, Qdrant, Neo4j, ClickHouse, OpenSearch, S3 and tombstone records with cryptographic proof-of-deletion hashes, per-workspace data residency enforcement at query time, Data Loss Prevention (DLP) scanning of tool outputs / payloads / logs / artifacts, Privacy Impact Assessment workflow with privacy-officer approval, and first-time AI disclosure + consent tracking for end users. Feature UPD-023 in the audit-pass constitution; implements FR-466 through FR-470 and FR-510. Enforces constitution rules 15 (cascade deletion), 16 (DSR tombstones), 18 (regional residency enforcement), and AD-17 (tombstone-based RTBF proof)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Data subject exercises their right to erasure with full cascade (Priority: P1) 🎯 MVP

A European customer contacts support and exercises their GDPR Article 17 right to be forgotten. A privacy officer receives the request, verifies the subject's identity, and opens a Data Subject Request (DSR) of type `erasure` on the platform. The platform enumerates every store and bucket the subject's data lives in (PostgreSQL rows across `users`, workspaces, memberships, interactions, memory, audit, executions; Qdrant vectors; Neo4j nodes; ClickHouse rows; OpenSearch documents; S3 objects), executes the deletion against each one, and produces a tombstone record carrying a cryptographic hash of the deletion manifest. The subject (or their legal representative) can request a signed copy of the tombstone as proof of compliance. The audit chain (from UPD-024) preserves every action taken.

**Why this priority**: Erasure is the most operationally risky and legally pressing of the six data-subject rights. Without it, the organisation cannot meet GDPR Article 17 or CCPA §1798.105, which are the two most enforced privacy provisions. MVP because the feature as a whole is structured around getting erasure right; the other five DSR types (access, rectification, portability, restriction, objection) are variations that build on the same primitive.

**Independent Test**: Create a test subject, generate data across all six data stores, open an erasure DSR, run it, and verify: (a) zero rows remain referencing the subject in any store, (b) a tombstone row exists with a non-null `proof_hash` matching the SHA-256 of the canonical deletion manifest, (c) the DSR record shows `status='completed'` with `completion_proof_hash` populated, (d) the audit chain (UPD-024) contains one entry per stage. No other user story needs to be implemented for this to deliver value.

**Acceptance Scenarios**:

1. **Given** a privacy officer with the permission to submit DSRs, **When** they open an erasure DSR naming a subject user, **Then** the DSR is persisted with `request_type='erasure'`, `status='received'`, `requested_by` set to the officer, and an audit chain entry recording the open.
2. **Given** an open erasure DSR, **When** the cascade-deletion orchestrator runs, **Then** it deletes (or nullifies, per the data-store-specific policy) every row, vector, node, document, and object referencing the subject across all six data stores, and records each step's affected counts in a structured `cascade_log` on the resulting tombstone.
3. **Given** the cascade-deletion runs to completion, **When** the tombstone is produced, **Then** it contains an `entities_deleted` JSONB enumerating the affected stores with counts, a `cascade_log` of per-stage outcomes, and a `proof_hash` equal to the SHA-256 of the canonical-JSON tombstone payload.
4. **Given** a DSR is complete, **When** a privacy officer fetches it, **Then** the response contains `status='completed'`, `completed_at`, and `completion_proof_hash` that equals the tombstone's `proof_hash`.
5. **Given** an audit or compliance officer requests a signed tombstone, **When** they call the export endpoint, **Then** a JSON document is returned containing the tombstone + an Ed25519 signature over its content (signed by the audit-chain's signing key from UPD-024), verifiable against the published public key.
6. **Given** the cascade-deletion fails partway (e.g. Qdrant unreachable), **When** the orchestrator reaches the failure, **Then** the DSR transitions to `status='failed'`, the partial `cascade_log` is persisted with the specific stage and error, an operator notification fires, and the DSR can be retried idempotently.

---

### User Story 2 — End user sees AI disclosure and grants consent on first agent interaction (Priority: P1)

A first-time end user opens a conversation with an agent. Before the first message is dispatched, the UI shows an AI disclosure panel: "You are interacting with an AI system. Your messages may be used to improve the agent's responses; you can decline and still use the service. See our privacy policy for full details." The user grants or declines each of three explicit consent types (AI interaction, data collection, training use). Their choices are persisted as `consent_records`. Revoking consent later removes it immediately; the agent will not reuse the user's historic messages for training after revocation.

**Why this priority**: The EU AI Act and CCPA both require clear disclosure + explicit consent for AI interactions. P1 alongside US1 because the disclosure is a user-facing legal requirement and the backend is trivial once the consent table exists; shipping US1 without US2 leaves the platform exposing GDPR erasure capabilities to a population that was never properly informed about the AI system to begin with.

**Independent Test**: Create a new user; open a conversation with an agent; verify the AI disclosure is shown before any message dispatch; grant one consent type and decline another; verify `consent_records` persists both choices with correct `granted: true/false`; revoke the granted consent; verify the revocation is reflected with `revoked_at` populated.

**Acceptance Scenarios**:

1. **Given** a user has no prior `consent_records` for a given agent or workspace, **When** they initiate their first conversation, **Then** the UI surfaces the AI disclosure with explicit toggles for `ai_interaction`, `data_collection`, and `training_use` consent types.
2. **Given** the user submits their consent choices, **When** the submission is persisted, **Then** three rows are written to `consent_records` with `granted_at` set and no `revoked_at`, one per consent_type.
3. **Given** a user has granted `training_use` consent, **When** they revoke it, **Then** the row's `revoked_at` is populated with the revocation timestamp and the agent composition service excludes that user's messages from training corpora going forward (the revocation does not retroactively alter past training, but no new use occurs).
4. **Given** a user has declined `data_collection`, **When** they continue using the platform, **Then** data collection for analytics/improvement purposes is suppressed for that user (opt-out honoured); the user can still use the platform.
5. **Given** an auditor queries consent history for a user, **When** the query runs, **Then** it returns every consent event (grants + revocations) with timestamps, producing an accountable history.

---

### User Story 3 — Privacy officer approves a Privacy Impact Assessment (PIA) before agent deployment (Priority: P2)

A creator requests certification of a new agent that handles sensitive data (e.g. an HR agent that reads employee records). Before the certification can complete, a privacy officer must conduct a Privacy Impact Assessment. The PIA workflow forces the officer to document: data categories processed, legal basis for processing, retention policy, identified risks, and mitigations. Once approved, the agent can be certified and deployed. If the PIA is rejected, the agent cannot deploy until gaps are addressed. PIAs are required for any agent whose declared data categories include PII, PHI, financial, or confidential classifications.

**Why this priority**: GDPR Article 35 requires a Data Protection Impact Assessment for high-risk processing. The PIA workflow is the organisation's evidence that it performed the assessment. P2 because the feature is most valuable once agents are being certified regularly (after US1 + US2 ship); it is not a blocker to baseline GDPR compliance.

**Independent Test**: Create an agent declaring data_categories including PII. Attempt to certify it; verify certification is blocked with `PIAR_REQUIRED` error. Submit a PIA draft; officer reviews; approve. Re-attempt certification; verify it proceeds. Reject a different PIA; verify the affected agent's certification remains blocked.

**Acceptance Scenarios**:

1. **Given** an agent declares any `data_category` in {`pii`, `phi`, `financial`, `confidential`}, **When** a creator requests certification, **Then** certification is blocked until a PIA in status `approved` exists for that agent.
2. **Given** a creator submits a PIA draft, **When** it is saved, **Then** the PIA is persisted with `status='draft'`, the data_categories, legal_basis, retention_policy, risks, and mitigations fields all populated; empty/null required fields are rejected.
3. **Given** a PIA in `draft`, **When** a privacy officer reviews and approves, **Then** `status='approved'`, `approved_by` and `approved_at` are set, an audit chain entry records the approval, and any pending certification for the agent can now proceed.
4. **Given** a PIA in `draft`, **When** a privacy officer rejects it with feedback, **Then** `status='rejected'`, the feedback is recorded, and the blocked certification remains blocked until a revised PIA is re-submitted and approved.
5. **Given** a PIA was approved for an agent, **When** the agent's declared data_categories change materially, **Then** the existing PIA is invalidated (`status='superseded'`) and a new PIA is required for the changed categories.

---

### User Story 4 — Workspace admin enforces data residency (Priority: P2)

A workspace admin at a German subsidiary configures data residency for their workspace: region `eu-central-1`, no cross-region transfers allowed. From that moment, any query, write, or event that would move the workspace's data outside `eu-central-1` is rejected at query time with a residency error. If the admin later adds `eu-west-1` to `allowed_transfer_regions`, transfers to that region succeed; others continue to fail. Agents running in other regions cannot read this workspace's data unless their region is in the allowlist.

**Why this priority**: Residency is a hard enterprise requirement for many EU customers and a compliance multiplier. P2 because it becomes valuable when the platform operates in multiple regions (a future state; single-region installs see it as a no-op).

**Independent Test**: Configure `data_residency_configs` for a workspace with `region_code='eu-central-1'` and empty `allowed_transfer_regions`. Simulate a query from a different region; verify it is rejected. Add `eu-west-1` to the allowlist; verify the same query from `eu-west-1` succeeds.

**Acceptance Scenarios**:

1. **Given** a workspace has a `data_residency_configs` row with `region_code='eu-central-1'` and empty `allowed_transfer_regions`, **When** a query originating from `us-east-1` targets that workspace's data, **Then** the query is rejected at query time with a structured `RESIDENCY_VIOLATION` error.
2. **Given** a workspace's residency config allows `eu-west-1`, **When** a query from `eu-west-1` targets it, **Then** the query succeeds.
3. **Given** a workspace has no residency config, **When** queries from any region target it, **Then** they all succeed (residency is opt-in; unconfigured means unrestricted — backward compatibility).
4. **Given** a workspace admin updates the residency config, **When** they remove a region from `allowed_transfer_regions`, **Then** subsequent queries from that region are rejected (change takes effect on the next query).
5. **Given** a cross-region query is rejected, **When** the event is logged, **Then** a structured residency-violation audit entry is written (audit chain, UPD-024) with the source region, target workspace, and actor.

---

### User Story 5 — Privacy officer configures DLP rules and reviews events (Priority: P2)

A privacy officer sets up DLP rules for the workspace: "US Social Security Numbers must be redacted in any tool output", "internal confidentiality-marked documents must block transmission to external tools". Agents running in the workspace have their tool inputs/outputs scanned by the DLP layer at runtime; matches trigger the configured action (redact, block, flag). Every DLP event is persisted with a match summary (not the full match content, to avoid echoing the PII); a dashboard shows event counts, rule hit rates, and false-positive triage.

**Why this priority**: DLP is the active detective control that prevents known categories of data leakage in real time. P2 because it complements US1 + US2's prevention+compliance story with active enforcement; without DLP, PII disclosure incidents only surface via reactive mechanisms.

**Independent Test**: Create a DLP rule with pattern matching US SSN format + action `redact`. Execute an agent whose tool output contains a synthetic SSN; verify the SSN is redacted in the returned output AND a `dlp_event` row exists referencing the rule + execution.

**Acceptance Scenarios**:

1. **Given** a privacy officer creates a DLP rule with `classification='pii'`, pattern matching SSN format, and `action='redact'`, **When** the rule is saved, **Then** it is persisted enabled by default and takes effect on the next tool invocation in the affected workspace.
2. **Given** an agent calls a tool whose output contains a match for an enabled DLP rule with `action='redact'`, **When** the tool gateway returns the output to the agent, **Then** the matching substring is replaced with `[REDACTED:{classification}]` before the agent sees it.
3. **Given** an agent produces output matching a rule with `action='block'`, **When** the guardrail pipeline processes the output, **Then** the response is blocked, a `dlp_event` is recorded, and the affected user sees a structured error.
4. **Given** a rule with `action='flag'`, **When** a match occurs, **Then** the output proceeds without modification BUT a `dlp_event` is recorded and a privacy-officer dashboard surface reflects the match.
5. **Given** a privacy officer reviews the DLP events, **When** they open the dashboard, **Then** they see events listed by rule, with per-rule hit counts and per-execution pointers, WITHOUT the full match content (match_summary is a category label, not PII).

---

### User Story 6 — Compliance auditor verifies tombstone chain integrity (Priority: P3)

An external compliance assessor is auditing the organisation's privacy posture. They request proof that a specific subject's data (whose erasure DSR was completed six months ago) was actually deleted. A compliance auditor opens the tombstone for that DSR, exports it as a signed document, and hands it to the assessor. The assessor independently verifies the Ed25519 signature against the platform's public key, then recomputes the SHA-256 of the canonical tombstone payload and confirms it matches the stored `proof_hash`. The DSR is corroborated by the audit chain (UPD-024), which is itself verifiable end-to-end. The assessor has a cryptographically-verifiable chain of custody without needing platform access.

**Why this priority**: The tombstone signing + external verification capability turns the erasure promise into an assessable attestation. P3 because US1 already produces tombstones with hashes; US6 adds the external-verification UX on top. Can ship incrementally once tombstones exist.

**Independent Test**: Run an erasure DSR (via US1 path). Fetch the signed tombstone export. Re-compute the SHA-256 of the canonical payload on an external client; verify it matches `proof_hash`. Re-verify the Ed25519 signature against the public key fetched from the audit-chain public-key endpoint; confirm signature valid.

**Acceptance Scenarios**:

1. **Given** an erasure DSR has been completed, **When** an auditor exports the tombstone via the admin API, **Then** the response is a signed JSON document containing `{tombstone, key_version, signature}` where `signature` is an Ed25519 signature over the canonical tombstone payload.
2. **Given** the signed tombstone is shared with an external assessor, **When** they recompute SHA-256 of the canonical payload and compare against `tombstone.proof_hash`, **Then** the hashes match 100% of the time.
3. **Given** the signed tombstone, **When** the assessor verifies the signature against the platform's public Ed25519 key, **Then** the signature is valid 100% of the time (key from UPD-024's `/api/v1/security/audit-chain/public-key` endpoint).
4. **Given** the signed tombstone payload has been altered, **When** verification runs, **Then** either the hash or the signature check fails, detecting the tamper.
5. **Given** the auditor cross-references the DSR against the audit chain (UPD-024), **When** they do, **Then** every stage of the DSR (received, cascade started, cascade completed, tombstone produced) appears as a chain entry linking to the DSR ID.

---

### Edge Cases

- **Subject appears in data stores the cascade orchestrator doesn't know about**: New data stores added to the platform after the cascade was implemented. Mitigation: a registration table listing every data store the cascade handles; CI checks that every new store added to the platform also registers a deletion adapter.
- **Cascade partial failure mid-run**: One store succeeds, another fails. The DSR goes to `status='failed'` with `cascade_log` showing which stages succeeded/failed; re-running is idempotent (successful stores skip the already-deleted rows).
- **Access DSR includes data that belongs to another subject**: E.g. a conversation mentions a third party. The export redacts non-subject PII via the DLP scanner before returning.
- **Right-to-be-forgotten for a subject who is a creator**: Their agents remain but are disowned (transferred to `platform` owner) so they keep working for other consumers. Their name disappears; the agents persist.
- **Residency config removed**: Transitioning from "residency enforced" to "no residency config" relaxes restrictions; this is logged as a residency change but does not retroactively rewrite previous queries.
- **DLP rule matches millions of times per day**: Very high-match patterns produce noise. Events are retained for 90 days; aggregated counts beyond 90 days; operators can tune patterns to reduce noise.
- **PIA approved then the agent changes**: Material change (new data category, new legal basis) invalidates the PIA; `status='superseded'`. The creator must submit a revised PIA.
- **Consent revoked while training is mid-run**: Training uses a snapshot; already-started jobs complete (no retroactive revocation of in-flight work), but subsequent jobs exclude the user.
- **Cross-region query from an unknown region**: Treat unknown regions as disallowed (fail-closed); mitigate with operator notifications.
- **Tombstone lookup after the subject's row is gone**: Tombstones do NOT contain the subject's PII — only counts + hashes — so lookups work without the subject existing in the users table.
- **First-interaction consent bypass in an automated workflow**: Non-interactive flows (e.g. a cron-triggered agent) are scoped per service account; consent is managed at the service-account level, not the interactive-user level.
- **DSR submitted by a user who is not the subject (legal rep, guardian)**: The DSR supports `requested_by != subject_user_id`; legal-basis field records the authorisation.

## Requirements *(mandatory)*

### Functional Requirements

**Data Subject Request (DSR) handling**

- **FR-001**: The platform MUST support six DSR request types: `access`, `rectification`, `erasure`, `portability`, `restriction`, `objection` (GDPR Articles 15, 16, 17, 20, 18, 21; CCPA equivalents).
- **FR-002**: A DSR MUST record the subject user, the requester (privacy officer OR an authenticated legal representative), the legal basis, the request type, and a status lifecycle (`received → in_progress → completed | failed`).
- **FR-003**: Every DSR state transition MUST emit an audit chain entry (UPD-024, constitution rule 9) and a Kafka event on `privacy.dsr.received` / `privacy.dsr.completed` / `privacy.deletion.cascaded`.
- **FR-004**: A completed DSR MUST carry a `completion_proof_hash` equal to the SHA-256 of the DSR's canonical completion payload (including the tombstone ID if erasure).

**Right-to-be-forgotten cascade deletion**

- **FR-005**: The cascade-deletion orchestrator MUST delete or null-replace all data referencing the subject across: PostgreSQL rows (every table with a `user_id` / `subject_user_id` / `created_by` column referencing `users.id`), Qdrant vectors (every collection), Neo4j nodes and edges, ClickHouse rows, OpenSearch documents, and S3 objects in every configured bucket.
- **FR-006**: The cascade-deletion orchestrator MUST produce a tombstone record per FR-007, even if some stages failed (the tombstone records partial completion).
- **FR-007**: A tombstone record MUST carry: `subject_user_id`, `entities_deleted` (JSONB with per-store counts), `cascade_log` (per-stage outcome), and `proof_hash` (SHA-256 of the canonical tombstone payload, computed deterministically per AD-17).
- **FR-008**: Tombstones MUST NEVER contain the subject's PII — only counts, stage names, and hashes. The tombstone is itself an immutable audit artefact.
- **FR-009**: Re-running a cascade deletion for the same subject MUST be idempotent: already-deleted rows are skipped; `cascade_log` is appended, not overwritten.
- **FR-010**: The cascade-deletion orchestrator MUST support a dry-run mode that enumerates what would be deleted without performing any deletion.
- **FR-011**: Signed tombstones MUST be exportable as `{tombstone_payload, key_version, signature}` where `signature` is an Ed25519 signature over the canonical payload using the audit-chain signing key (UPD-024).

**Data residency enforcement**

- **FR-012**: Workspace residency is optional: a workspace with no `data_residency_configs` row operates without residency restrictions (backward compatibility).
- **FR-013**: A workspace with a residency config MUST have queries from regions not in `region_code` or `allowed_transfer_regions` rejected at query time with a structured `RESIDENCY_VIOLATION` error. Enforcement at query time, not at install time.
- **FR-014**: Every residency violation MUST be audit-chain-logged (UPD-024) with the source region, target workspace, and actor.
- **FR-015**: Changes to residency config MUST take effect on the next query — no service restart required. Propagation latency budget ≤ 60 seconds.
- **FR-016**: Cross-region query origin is determined by an authenticated platform header `X-Origin-Region`; unauthenticated queries without the header are treated as `unknown` and subject to the same rules.

**Data Loss Prevention (DLP)**

- **FR-017**: The platform MUST support DLP rules scoped per-workspace with: `classification` (`pii` / `phi` / `financial` / `confidential`), a pattern (regex or string), and an `action` (`redact` / `block` / `flag`).
- **FR-018**: DLP rules MUST be invoked on: tool outputs (before return to agent), tool payloads (before dispatch to external tools), log streams (before structured emission), and large artefacts (before storage in S3).
- **FR-019**: Actions:
  - `redact` replaces the matching substring with `[REDACTED:{classification}]`.
  - `block` fails the request with a structured error and logs the event.
  - `flag` allows the content through but records the event for later review.
- **FR-020**: Every DLP event MUST be persisted with `rule_id`, optional `execution_id`, a `match_summary` (a **category label only**, NOT the full matched text, to prevent echoing PII), the `action_taken`, and timestamp.
- **FR-021**: Platform-seeded DLP rules (SSN, credit card, email, JWT, API key prefixes) MUST ship enabled per-workspace; operators can disable specific rules but cannot alter their patterns in v1.

**Privacy Impact Assessment (PIA)**

- **FR-022**: A PIA MUST record: subject (agent / workspace / workflow), `data_categories`, `legal_basis`, `retention_policy`, `risks`, `mitigations`, status (`draft` / `under_review` / `approved` / `rejected` / `superseded`), and the approver.
- **FR-023**: Any agent whose declared data_categories include `pii`, `phi`, `financial`, or `confidential` MUST have an `approved` PIA before certification can complete. Certification requests for such agents without an approved PIA MUST be rejected with a structured `PIA_REQUIRED` error.
- **FR-024**: PIA approval transitions require `privacy_officer` role (or `superadmin`). The requester cannot self-approve (rule 33, 2PA).
- **FR-025**: Material change to an agent's declared data_categories MUST invalidate the agent's existing approved PIA (`status='superseded'`).
- **FR-026**: Every PIA lifecycle event MUST emit an audit chain entry and a `privacy.pia.approved` / `privacy.pia.rejected` / `privacy.pia.superseded` Kafka event.

**Consent and AI disclosure**

- **FR-027**: The platform MUST track three consent types per user: `ai_interaction`, `data_collection`, `training_use`.
- **FR-028**: The first time a user initiates a conversation with any agent, the UI MUST surface an AI disclosure that names: (a) the nature of AI interaction, (b) any data collection, (c) training-use intent, and a link to the privacy policy. The user MUST explicitly grant or decline each consent type before the first message is dispatched.
- **FR-029**: Consent revocation takes effect immediately; subsequent agent turns honour the revocation. In-flight training jobs that have already snapshotted their corpus are allowed to complete without retroactive exclusion; subsequent training jobs exclude revoked users.
- **FR-030**: An auditor MUST be able to query the full consent history for any user with timestamps for grants and revocations.
- **FR-031**: The user's consent state MUST propagate to the agent composition service (excluded from training corpora when `training_use=false`) and to the analytics pipeline (suppressed when `data_collection=false`).

### Key Entities *(include if feature involves data)*

- **Data Subject Request (DSR)** — a recorded request to exercise one of six GDPR/CCPA rights on behalf of a subject user, with lifecycle (received / in_progress / completed / failed), requester, legal basis, and completion proof hash.
- **Deletion Tombstone** — an immutable record of a cascade deletion for a specific subject, carrying `entities_deleted`, `cascade_log`, and `proof_hash`. Never contains PII.
- **Data Residency Config** — a per-workspace binding to a primary region and an optional allowlist of transfer regions; absence of the row means no restriction.
- **DLP Rule** — a per-workspace pattern + classification + action that the DLP scanner consults on tool outputs, payloads, logs, and artefacts.
- **DLP Event** — a persisted detection event capturing the rule hit, the execution (if any), a classification-label-only match summary, and the action taken.
- **Privacy Impact Assessment (PIA)** — a structured assessment of an agent / workspace / workflow's privacy risks, with required fields (data categories, legal basis, retention, risks, mitigations), a status lifecycle, and a privacy-officer approval.
- **Consent Record** — a per-user, per-consent-type record of grant and optional revocation timestamps; governs agent interaction, data collection, and training use.
- **Region Origin Context** — a per-request attribute identifying the origin region of the caller; used by the residency enforcer.
- **Cascade Adapter** — a registered component that handles deletion in a specific data store (PostgreSQL, Qdrant, Neo4j, ClickHouse, OpenSearch, S3). Every store must have an adapter.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every completed erasure DSR produces a tombstone with a non-null `proof_hash` that equals the SHA-256 of the canonical tombstone payload; verified externally by recomputing the hash on 100% of a quarterly random-sample audit.
- **SC-002**: For a completed erasure DSR, zero rows referencing the subject remain in any data store (PostgreSQL, Qdrant, Neo4j, ClickHouse, OpenSearch, S3) within 1 hour of DSR completion; verified by post-completion scan.
- **SC-003**: A cascade-deletion failure mid-run does not silently drop the DSR — 100% of failed DSRs transition to `status='failed'` with a complete `cascade_log` identifying the failing stage; verified by chaos testing (induced per-store failures).
- **SC-004**: An external assessor can verify a signed tombstone's hash and signature on an independent client in under 5 minutes using the documented verification steps and publicly-fetched key — demonstrating the tombstone is a self-contained attestation.
- **SC-005**: 100% of first-time agent conversations surface the AI disclosure + consent panel BEFORE the first message is dispatched; verified by a UI E2E test in the user journey suite (feature 072).
- **SC-006**: Consent revocation propagates to downstream systems (agent composition training exclusion, analytics suppression) within 5 minutes; verified by automated propagation test.
- **SC-007**: Cross-region query enforcement: when a workspace has a residency config, 100% of queries originating from regions outside the allowed set are rejected; zero false-passes verified by residency-violation synthetic tests.
- **SC-008**: DLP rules with `action='redact'` prevent the full match from appearing in any downstream tool output on 100% of hits; verified by integration tests seeding synthetic patterns.
- **SC-009**: Every agent with declared PII / PHI / financial / confidential data categories cannot complete certification without an `approved` PIA; verified by the certification-flow integration tests.
- **SC-010**: Cascade-deletion performance: a subject with 1 million data-store rows is fully cascaded in under 15 minutes on reference hardware, with `cascade_log` accurately recording per-store counts.
- **SC-011**: 100% of DSR state transitions, PIA approvals/rejections, DLP events, and residency violations produce corresponding audit chain entries in UPD-024's chain within 5 seconds.

## Assumptions

- The feature depends on UPD-024's `AuditChainService` for audit chain entries and its Ed25519 signing key for tombstone attestation. Env-var fallback signing key acceptable during UPD-024's rollout.
- The six data stores to cascade are those currently in use by the platform (PostgreSQL, Qdrant, Neo4j, ClickHouse, OpenSearch, S3). New stores added later require a new `Cascade Adapter` registration; existing CI catches untracked stores.
- "Subject" means any natural person for whom the platform processes personal data — default mapping is to rows in the `users` table. Third-party mentions in free-text (e.g. a mentioned name in a conversation) are handled by access-DSR redaction, not by cascade deletion targeting the mentioned party.
- Legal basis for erasure is typically "consent withdrawn" or "no longer necessary"; the platform does not adjudicate legal basis — it records what the privacy officer enters and preserves the record.
- Cascade deletion is a destructive operation and MUST be staged: a `scheduled` status with a configurable delay (default: immediate; operators can set a 24-hour hold for human override) before the orchestrator fires. Emergency override is possible via superadmin.
- DLP pattern set ships with a seeded default covering SSN, credit card, IBAN, phone number, email, common API key prefixes, JWT, and long-form base64; operators can disable rules per-workspace but cannot alter the seed.
- Residency config applies to data stored at rest for the workspace; in-transit encryption is independently handled by the platform's TLS configuration and is not in this feature's scope.
- The AI disclosure text is shipped in platform defaults in six languages (ties to UPD-030 i18n); operators can customise per-tenant text in a follow-up. This feature ships English defaults; full i18n is a follow-up.
- PIA templates (standard questionnaire forms for common data categories) are future work; v1 ships a free-form + structured-JSON template only.
- DLP events are retained for 90 days at full fidelity; aggregated counts are retained indefinitely in ClickHouse (analytics BC). Retention is configurable per workspace within platform floor.
- Tombstone retention is indefinite — tombstones are compliance evidence and cannot be pruned.
- The tombstone's canonical payload MUST be serialised with sorted JSON keys + no whitespace for deterministic SHA-256; any divergence between platform and external verifier's canonicalisation invalidates the hash.
- Users with blocked / archived states (from UPD-016 accounts) are NOT automatically triggered for erasure. Erasure is a separate, explicit DSR — account lifecycle and DSR lifecycle are independent.
